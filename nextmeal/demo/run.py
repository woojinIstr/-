"""Run the packaged app and a temporary local test account."""
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Timer
import webbrowser

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))


def add_example(app):
    from app.main import DEMO_USER
    from app.workspace import apply, bootstrap, day_after, today

    state = bootstrap([], [], [], [], [])

    def change(action, **payload):
        nonlocal state
        state, _ = apply(state, action, payload)

    change('lot.quick_add', items=[{'name':'달걀','quantity':2,'unit':'count'},
                                   {'name':'삼겹살','quantity':250,'unit':'g'},
                                   {'name':'햇반','quantity':1,'unit':'pack','pack_size':210,'pack_label':'개'}])
    change('ingredient.create', name='양파', unit='g')
    change('ingredient.create', name='당근', unit='count')
    ingredients = {row['name']:row['id'] for row in state['ingredients']}
    day = today()
    tomorrow = day_after(day,1)
    for name, ingredient, quantity, unit, date, slot in (
        ('삼겹살 저녁','삼겹살',150,'g',day,'dinner'),
        ('양파 볶음밥','양파',200,'g',tomorrow,'breakfast'),
        ('당근구이','당근',2,'count',tomorrow,'dinner'),
    ):
        change('recipe.save', name=name, base_servings=1, minutes=15,
               ingredients=[{'ingredient_id':ingredients[ingredient],'quantity':quantity,'unit':unit}])
        change('meal.save', date=date, slot=slot, servings=1, recipe_id=state['recipes'][-1]['id'])
    change('shopping.add', name='양파', quantity=70, unit='g')
    app.state.workspace_repository.put(DEMO_USER, '', -1, state)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--example', action='store_true', help='Load the presentation scenario')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='nextmeal-demo-') as tmp:
        os.environ.update(APP_ENV='development', APP_MODE='local', SQLITE_PATH=str(Path(tmp)/'demo.db'),
                          OPENROUTER_API_KEY='', OPENAI_API_KEY='')
        from app.serve import create_app
        app = create_app()
        if args.example:
            add_example(app)
        url = f'http://127.0.0.1:{args.port}/?page={"meals" if args.example else "home"}'
        print(url, flush=True)
        if not args.no_browser:
            timer = Timer(1, webbrowser.open, args=(url,))
            timer.daemon = True
            timer.start()
        uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    run()
