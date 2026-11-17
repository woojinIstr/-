
import unittest
from recommendation.engine import recommend


class TestRecommendation(unittest.TestCase):

    def setUp(self):
        self.workspace = {
            "ingredients": [
                {"id": "rice", "name": "밥", "unit": "g"},
                {"id": "egg", "name": "계란", "unit": "count"}
            ],
            "inventory": [
                {
                    "ingredient_id": "rice",
                    "quantity": 300,
                    "unit": "g",
                    "archived": False
                },
                {
                    "ingredient_id": "egg",
                    "quantity": 2,
                    "unit": "count",
                    "archived": False
                }
            ],
            "recipes": [
                {
                    "id": "fried_rice",
                    "name": "계란볶음밥",
                    "minutes": 15,
                    "base_servings": 1,
                    "archived": False,
                    "ingredients": [
                        {
                            "ingredient_id": "rice",
                            "quantity": 200,
                            "unit": "g"
                        },
                        {
                            "ingredient_id": "egg",
                            "quantity": 1,
                            "unit": "count"
                        }
                    ]
                }
            ]
        }

    def test_available_recipe(self):
        result = recommend(self.workspace)
        self.assertTrue(result[0]["ready"])

    def test_missing_ingredients(self):
        self.workspace["inventory"][1]["quantity"] = 0
        result = recommend(self.workspace)
        self.assertFalse(result[0]["ready"])
        self.assertEqual(result[0]["missing"][0]["name"], "계란")

    def test_excluded_ingredient(self):
        result = recommend(
            self.workspace,
            excluded_ids=["egg"]
        )
        self.assertEqual(len(result), 0)

    def test_max_cooking_time(self):
        result = recommend(
            self.workspace,
            max_minutes=10
        )
        self.assertEqual(len(result), 0)

    def test_servings(self):
        result = recommend(
            self.workspace,
            servings=3
        )
        self.assertFalse(result[0]["ready"])


if __name__ == "__main__":
    unittest.main()
