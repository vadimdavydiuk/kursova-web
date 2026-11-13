"""Прямі unit-тести бізнес-логіки та окремі перевірки безпеки."""
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = os.urandom(32).hex()
os.environ.pop('ADMIN_PASSWORD', None)
from app import app, db, Order, User, cart_items, cart_total, unit_price, validate_checkout, seed


class CartUnitTests(unittest.TestCase):
    def setUp(self):
        self.context = app.test_request_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        from flask import session
        self.session = session
        self.lookup = patch('app.db.session.get', return_value=SimpleNamespace(id=2, price=239))
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def test_empty_cart(self):
        self.assertEqual(cart_items(), [])

    def test_round_unit_before_quantity(self):
        self.session['cart'] = {'2:large': 2}
        item, = cart_items()
        self.assertEqual((item['unit'], item['line']), (311, 622))

    def test_multiple_sizes(self):
        self.session['cart'] = {'2:small': 1, '2:medium': 3}
        self.assertEqual([x['line'] for x in cart_items()], [203, 717])

    def test_missing_pizza(self):
        with patch('app.db.session.get', return_value=None):
            self.session['cart'] = {'999:large': 2}
            self.assertEqual(cart_items(), [])

    def test_invalid_size(self):
        self.session['cart'] = {'2:huge': 1}
        self.assertEqual(cart_items(), [])

    def test_invalid_quantities(self):
        for qty in [0, -1, 11, '2', 1.5, True, None]:
            with self.subTest(quantity=qty):
                self.session['cart'] = {'2:large': qty}
                self.assertEqual(cart_items(), [])

    def test_malformed_keys(self):
        for key in ['oops', 'x:large', '2:large:extra', 2]:
            with self.subTest(key=key):
                self.session['cart'] = {key: 1}
                self.assertEqual(cart_items(), [])

    def test_non_dictionary_cart(self):
        self.session['cart'] = ['2:large']
        self.assertEqual(cart_items(), [])

    def test_supplied_total(self):
        self.assertEqual(cart_total([{'line': 622}, {'line': 189}]), 811)

    def test_empty_total_avoids_lookup(self):
        with patch('app.cart_items', side_effect=AssertionError('unexpected lookup')):
            self.assertEqual(cart_total([]), 0)

    def test_total_reads_cart_when_omitted(self):
        with patch('app.cart_items', return_value=[{'line': 311}, {'line': 189}]):
            self.assertEqual(cart_total(), 500)

    def test_half_rounds_up(self):
        self.assertEqual(unit_price(205, 'large'), 267)

    def test_all_240_menu_combinations(self):
        for base in [189,239,259,229,269,249,219,259]:
            for size, factor in [('small',85),('medium',100),('large',130)]:
                for qty in range(1,11):
                    with self.subTest(base=base,size=size,quantity=qty):
                        self.session['cart'] = {'2:'+size:qty}
                        with patch('app.db.session.get',return_value=SimpleNamespace(id=2,price=base)):
                            item, = cart_items()
                            self.assertEqual(item['line'], ((base*factor+50)//100)*qty)


class CheckoutValidationUnitTests(unittest.TestCase):
    def valid_data(self):
        return dict(name='Олена', phone='+380671234567', address='вул. Тестова, 1', comment='')

    def test_valid_fields(self):
        self.assertTrue(validate_checkout(self.valid_data())[1])

    def test_strips_whitespace(self):
        clean, valid = validate_checkout({k: '  '+v+'  ' for k,v in self.valid_data().items()})
        self.assertTrue(valid)
        self.assertEqual(clean, self.valid_data())

    def test_missing_fields(self):
        for field in ('name', 'phone', 'address'):
            data = self.valid_data()
            del data[field]
            with self.subTest(field=field):
                self.assertFalse(validate_checkout(data)[1])

    def test_minimum_lengths(self):
        for field, value in [('name','А'), ('address','вул'), ('phone','123456789')]:
            with self.subTest(field=field):
                self.assertFalse(validate_checkout({**self.valid_data(), field:value})[1])

    def test_maximum_lengths(self):
        for field, value in [('name','А'*101), ('address','А'*201), ('phone','1'*13), ('comment','А'*2001)]:
            with self.subTest(field=field):
                self.assertFalse(validate_checkout({**self.valid_data(), field:value})[1])

    def test_boundary_values(self):
        self.assertTrue(validate_checkout(dict(name='Ан',address='Дім 1',phone='1234567890'))[1])

    def test_optional_comment(self):
        data = self.valid_data()
        del data['comment']
        clean, valid = validate_checkout(data)
        self.assertTrue(valid)
        self.assertEqual(clean['comment'], '')


class SecurityIntegrationTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.context = app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        db.drop_all()
        db.create_all()
        seed()
        self.client = app.test_client()

    def post(self, path, data=None):
        self.client.get('/login')
        with self.client.session_transaction() as state:
            token = state['csrf_token']
        return self.client.post(path, data={**(data or {}), 'csrf_token':token})

    def test_all_post_routes_reject_missing_and_wrong_csrf(self):
        self.client.get('/login')
        paths = [r.rule.replace('<int:order_id>','1').replace('<int:message_id>','1')
                 for r in app.url_map.iter_rules() if 'POST' in r.methods]
        for path in paths:
            for data in ({}, {'csrf_token':'wrong-token'}):
                with self.subTest(path=path, token=data):
                    self.assertEqual(self.client.post(path,data=data).status_code,400)
        self.assertEqual(Order.query.count(),0)

    def test_all_rendered_forms_have_csrf(self):
        import re
        with self.client.session_transaction() as state:
            state['is_admin'] = True
        self.post('/cart/add', {'pizza_id':1,'quantity':1})
        self.post('/checkout', {'name':'Тест','phone':'1234567890','address':'Дім 1'})
        self.post('/contact', {'name':'Тест','phone':'1234567890','message':'Повідомлення'})
        self.post('/cart/add', {'pizza_id':1,'quantity':1})
        count = 0
        for path in ('/', '/menu', '/cart', '/login', '/admin'):
            html = self.client.get(path).get_data(as_text=True)
            for form in re.findall(r'<form\b.*?</form>',html,flags=re.S):
                if 'method="post"' in form:
                    count += 1
                    self.assertIn('name="csrf_token"',form)
        self.assertGreaterEqual(count,9)

    def test_order_owner_stranger_and_admin(self):
        self.post('/cart/add', {'pizza_id':1,'quantity':1})
        response = self.post('/checkout', {'name':'Тест','phone':'1234567890','address':'Дім 1'})
        self.assertEqual(self.client.get(response.location).status_code,200)
        stranger = app.test_client()
        self.assertEqual(stranger.get(response.location).status_code,404)
        with stranger.session_transaction() as state:
            state['is_admin'] = True
        self.assertEqual(stranger.get(response.location).status_code,200)

    def test_invalid_checkout_does_not_write(self):
        self.post('/cart/add', {'pizza_id':1,'quantity':1})
        self.post('/checkout', {'name':'А','phone':'123','address':'Дім'})
        self.assertEqual(Order.query.count(),0)

    def test_no_default_admin(self):
        self.assertEqual(User.query.count(),0)

    def test_login_hides_demo_credentials(self):
        html = self.client.get('/login').get_data(as_text=True)
        self.assertNotIn('Демодоступ',html)
        self.assertNotIn('admin'+'123',html)

    def test_zero_quantity_rejected(self):
        self.post('/cart/add', {'pizza_id':1,'quantity':0})
        with self.client.session_transaction() as state:
            self.assertEqual(state.get('cart',{}),{})

    def test_non_ascii_csrf_is_rejected(self):
        self.client.get('/login')
        self.assertEqual(self.client.post('/login',data={'csrf_token':'невірний'}).status_code,400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
