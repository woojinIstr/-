from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from app.workspace import active_followups, apply, bootstrap


class MealFollowupTests(TestCase):
    def setUp(self):
        clock = patch('app.workspace.today', return_value='2026-11-28')
        self.today = clock.start()
        self.addCleanup(clock.stop)
        self.state = bootstrap([], [], [], [], [])
        self.command('ingredient.create', name='양파', unit='g')
        self.command('recipe.save', name='양파구이', minutes=10, base_servings=1,
                     ingredients=[dict(ingredient_id=self.state['ingredients'][0]['id'], quantity=100, unit='g')])
        self.recipe = self.state['recipes'][0]['id']

    def command(self, action, **payload):
        self.state, _ = apply(self.state, action, payload)

    def plan(self, day, slot):
        self.command('meal.save', recipe_id=self.recipe, date=day, slot=slot, servings=1)
        return self.state['meals'][-1]['id']

    def eat_out(self, meal):
        self.command('meal.state', id=meal, status='eating_out')

    def test_day_after_with_no_plan_can_choose_and_save_once(self):
        source = self.plan('2026-11-28', 'breakfast')
        self.eat_out(source)
        self.today.return_value = '2026-11-29'
        self.assertEqual(active_followups(self.state)[source], dict(date='2026-11-29', slot='breakfast', target_id=None))
        payload = dict(after_eating_out=source, recipe_id=self.recipe, date='2026-11-29', slot='lunch', servings=1)
        self.command('meal.save', **payload)
        self.assertEqual(self.state['meal_followups'], {})
        with self.assertRaises(HTTPException):
            self.command('meal.save', **payload)
        self.assertEqual(len(self.state['meals']), 2)

    def test_close_or_restore_and_restart(self):
        source = self.plan('2026-11-28', 'dinner')
        self.eat_out(source)
        self.command('meal.skip_followup', id=source)
        self.assertEqual(self.state['meals'][0]['status'], 'eating_out')
        self.assertEqual(active_followups(self.state), {})
        self.command('meal.state', id=source, status='planned')
        self.eat_out(source)
        self.assertIn(source, active_followups(self.state))
        self.command('meal.state', id=source, status='planned')
        self.assertEqual(active_followups(self.state), {})

    def test_two_skipped_meals_can_share_one_future_target(self):
        first = self.plan('2026-11-28', 'breakfast')
        second = self.plan('2026-11-28', 'lunch')
        target = self.plan('2026-11-29', 'dinner')
        self.eat_out(second)
        self.eat_out(first)
        self.assertEqual({row['target_id'] for row in self.state['meal_followups'].values()}, {target})
        self.assertEqual(set(self.state['meal_followups']), {first, second})
        self.command('meal.save', id=target, after_eating_out=second, recipe_id=self.recipe,
                     date='2026-11-29', slot='dinner', servings=1)
        self.assertEqual(active_followups(self.state), {})

    def test_stale_target_does_not_overwrite_another_meal(self):
        source = self.plan('2026-11-28', 'dinner')
        target = self.plan('2026-11-29', 'lunch')
        other = self.plan('2026-11-30', 'dinner')
        self.eat_out(source)
        with self.assertRaises(HTTPException):
            self.command('meal.save', id=other, after_eating_out=source, recipe_id=self.recipe,
                         date='2026-11-30', slot='dinner', servings=1)
        self.command('meal.state', id=target, status='cancelled')
        self.assertEqual(active_followups(self.state), {})
        with self.assertRaises(HTTPException):
            self.command('meal.save', id=target, after_eating_out=source, recipe_id=self.recipe,
                         date='2026-11-29', slot='lunch', servings=1)

    def test_past_suggestions_expire_and_never_change_stock(self):
        source = self.plan('2026-11-28', 'lunch')
        self.eat_out(source)
        original = deepcopy(self.state)
        self.today.return_value = '2026-11-30'
        self.assertEqual(active_followups(self.state), {})
        self.assertEqual(self.state, original)

    def test_unambiguous_legacy_record_recovers_until_an_intervening_plan_save(self):
        source = self.plan('2026-11-28', 'dinner')
        target = self.plan('2026-11-29', 'lunch')
        self.eat_out(source)
        self.state.pop('meal_followups')
        self.assertEqual(active_followups(self.state)[source]['target_id'], target)
        self.command('shopping.add', name='물', quantity=1, unit='병')
        self.assertIn(source, self.state['meal_followups'])
        self.command('meal.save', id=target, recipe_id=self.recipe, date='2026-11-29', slot='lunch', servings=2)
        self.state.pop('meal_followups')
        self.assertEqual(active_followups(self.state), {})
