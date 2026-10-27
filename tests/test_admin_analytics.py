"""
tests/test_admin_analytics.py
-----------------------------
Focused tests for the database-backed admin analytics dashboard.

All tests use an isolated in-memory SQLite database. No network calls,
payment calls, or real application data are involved.
"""

import unittest
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from database import db
from models import User, Trek, Booking
from routes.admin import build_dashboard_analytics, format_currency


class AdminAnalyticsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret-key-for-testing',
        })
        self.client = self.app.test_client()
        self.today = date.today()

        with self.app.app_context():
            db.create_all()
            self._seed()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    @staticmethod
    def _at(day, hour=10):
        return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)

    def _seed(self):
        today = self.today

        admin = User(
            name='Admin', email='admin@test.com',
            password=generate_password_hash('pass123'),
            role='admin', status='Active',
        )
        staff = User(
            name='Guide', email='staff@test.com',
            password=generate_password_hash('pass123'),
            role='staff', status='Active',
        )
        user_one = User(
            name='Trekker One', email='user1@test.com',
            password=generate_password_hash('pass123'),
            role='user', status='Active',
        )
        user_two = User(
            name='Trekker Two', email='user2@test.com',
            password=generate_password_hash('pass123'),
            role='user', status='Active',
        )
        db.session.add_all([admin, staff, user_one, user_two])
        db.session.flush()
        self.admin_email = admin.email
        self.staff_email = staff.email
        self.user_email = user_one.email
        self.staff_id = staff.id
        self.user_one_id = user_one.id
        self.user_two_id = user_two.id

        alpine = Trek(
            trek_name='Alpine Ridge',
            location='Himachal Pradesh',
            difficulty='Moderate',
            duration='5 Days',
            available_slots=2,
            assigned_staff_id=staff.id,
            status='Open',
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=14),
        )
        forest = Trek(
            trek_name='Forest Trail',
            location='Uttarakhand',
            difficulty='Easy',
            duration='3 Days',
            available_slots=10,
            assigned_staff_id=None,
            status='Open',
            start_date=today + timedelta(days=20),
            end_date=today + timedelta(days=22),
        )
        completed = Trek(
            trek_name='Completed Peak',
            location='Sikkim',
            difficulty='Hard',
            duration='8 Days',
            available_slots=0,
            assigned_staff_id=staff.id,
            status='Completed',
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=24),
        )
        full = Trek(
            trek_name='Full Capacity',
            location='Nepal',
            difficulty='Hard',
            duration='6 Days',
            available_slots=0,
            assigned_staff_id=staff.id,
            status='Open',
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=10),
        )
        db.session.add_all([alpine, forest, completed, full])
        db.session.flush()
        self.alpine_id = alpine.trek_id
        self.forest_id = forest.trek_id
        self.completed_id = completed.trek_id
        self.full_id = full.trek_id

        # Verified revenue: 1000 + 2500 = INR 3,500.00
        bookings = [
            # Verified, active -> counted as confirmed and revenue.
            Booking(
                user_id=user_one.id, trek_id=alpine.trek_id,
                booking_date=self._at(today - timedelta(days=2)),
                status='Booked', payment_status='Verified',
                amount=1000.0, currency='INR',
                razorpay_order_id='order_verified_active',
            ),
            # Pending payment -> not confirmed, not revenue.
            Booking(
                user_id=user_two.id, trek_id=alpine.trek_id,
                booking_date=self._at(today - timedelta(days=1)),
                status='Booked', payment_status='Pending',
                amount=1000.0, currency='INR',
                razorpay_order_id='order_pending',
            ),
            # Cancelled + failed -> excluded from rankings and revenue.
            Booking(
                user_id=user_two.id, trek_id=forest.trek_id,
                booking_date=self._at(today),
                status='Cancelled', payment_status='Failed',
                amount=1000.0, currency='INR',
                razorpay_order_id='order_cancelled_failed',
            ),
            # Legacy completed -> confirmed, but never verified revenue.
            # Deliberately outside the 30-day trend window.
            Booking(
                user_id=user_one.id, trek_id=forest.trek_id,
                booking_date=self._at(today - timedelta(days=40)),
                status='Completed', payment_status='Legacy',
                amount=1000.0, currency='INR',
            ),
            # Verified completed -> counted as confirmed and revenue.
            Booking(
                user_id=user_one.id, trek_id=completed.trek_id,
                booking_date=self._at(today - timedelta(days=3)),
                status='Completed', payment_status='Verified',
                amount=2500.0, currency='INR',
                razorpay_order_id='order_verified_completed',
            ),
            # Failed payment -> pending payment KPI only.
            Booking(
                user_id=user_two.id, trek_id=full.trek_id,
                booking_date=self._at(today - timedelta(days=5)),
                status='Booked', payment_status='Failed',
                amount=1000.0, currency='INR',
                razorpay_order_id='order_failed',
            ),
            # Verified but cancelled -> excluded because refunds are untracked.
            Booking(
                user_id=user_one.id, trek_id=alpine.trek_id,
                booking_date=self._at(today - timedelta(days=4)),
                status='Cancelled', payment_status='Verified',
                amount=1000.0, currency='INR',
                razorpay_order_id='order_verified_cancelled',
            ),
            # Unpaid reservation -> pending payment KPI only.
            Booking(
                user_id=user_one.id, trek_id=forest.trek_id,
                booking_date=self._at(today - timedelta(days=6)),
                status='Booked', payment_status='Unpaid',
                amount=1000.0, currency='INR',
            ),
        ]
        db.session.add_all(bookings)
        db.session.commit()

    def _login(self, email, password='pass123'):
        return self.client.post(
            '/login', data={'email': email, 'password': password},
            follow_redirects=True,
        )

    def _analytics(self):
        with self.app.app_context():
            return build_dashboard_analytics(today=self.today)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------
    def test_dashboard_requires_authentication_and_admin_role(self):
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        for email in (self.user_email, self.staff_email):
            self.client.get('/logout')
            self._login(email)
            resp = self.client.get('/admin/dashboard', follow_redirects=True)
            self.assertIn(b'Administrator privileges required', resp.data)
            self.assertNotIn(b'Booking Trends', resp.data)

    # ------------------------------------------------------------------
    # KPI calculations
    # ------------------------------------------------------------------
    def test_kpi_calculations_from_representative_records(self):
        analytics = self._analytics()
        kpis = analytics['kpis']

        self.assertEqual(kpis['total_bookings'], 8)
        # Verified Booked, Legacy Completed, Verified Completed
        self.assertEqual(kpis['confirmed_bookings'], 3)
        # Alpine, Forest and Full Capacity all start in the future.
        self.assertEqual(kpis['upcoming_expeditions'], 3)
        # Pending + Failed + Unpaid reservations.
        self.assertEqual(kpis['pending_payments'], 3)

    def test_currency_formatting(self):
        self.assertEqual(format_currency('INR', 1000), 'INR 1,000.00')
        self.assertEqual(format_currency('INR', 3500.0), 'INR 3,500.00')
        self.assertEqual(format_currency(None, None), 'INR 0.00')

    # ------------------------------------------------------------------
    # Chart data
    # ------------------------------------------------------------------
    def test_booking_trend_aggregation(self):
        trend = self._analytics()['booking_trend']

        self.assertEqual(trend['window_days'], 30)
        self.assertEqual(len(trend['labels']), 30)
        self.assertEqual(len(trend['values']), 30)
        # Seven bookings fall inside the window; the 40-day-old legacy booking does not.
        self.assertEqual(trend['total'], 7)

        def count_for(days_ago):
            label = (self.today - timedelta(days=days_ago)).strftime('%b %d')
            return trend['values'][trend['labels'].index(label)]

        self.assertEqual(count_for(0), 1)  # cancelled/failed booking today
        self.assertEqual(count_for(1), 1)
        self.assertEqual(count_for(2), 1)
        self.assertEqual(count_for(3), 1)
        self.assertEqual(count_for(4), 1)
        self.assertEqual(count_for(5), 1)
        self.assertEqual(count_for(6), 1)
        self.assertEqual(count_for(7), 0)
        self.assertNotIn(
            (self.today - timedelta(days=40)).strftime('%b %d'),
            trend['labels'],
        )

    def test_booking_status_distribution_is_separate_from_payment_status(self):
        distribution = self._analytics()['booking_status']

        self.assertEqual(distribution['total'], 8)
        counts = dict(zip(distribution['labels'], distribution['values']))
        self.assertEqual(counts['Booked'], 4)
        self.assertEqual(counts['Cancelled'], 2)
        self.assertEqual(counts['Completed'], 2)
        # Payment statuses must never leak into the booking-status chart.
        self.assertNotIn('Verified', distribution['labels'])
        self.assertNotIn('Pending', distribution['labels'])

    def test_popular_treks_ranking_excludes_cancelled_bookings(self):
        treks = self._analytics()['popular_treks']

        self.assertEqual(len(treks), 4)
        self.assertEqual(treks[0]['trek_name'], 'Alpine Ridge')
        # Alpine Ridge has three bookings but one is cancelled: two remain.
        self.assertEqual(treks[0]['count'], 2)
        # Forest Trail has three bookings but one is cancelled: two remain.
        self.assertEqual(treks[1]['trek_name'], 'Forest Trail')
        self.assertEqual(treks[1]['count'], 2)
        self.assertEqual([trek['count'] for trek in treks], [2, 2, 1, 1])
        self.assertEqual(treks[2]['trek_name'], 'Completed Peak')
        self.assertEqual(treks[3]['trek_name'], 'Full Capacity')

    # ------------------------------------------------------------------
    # Verified revenue
    # ------------------------------------------------------------------
    def test_verified_revenue_excludes_unverified_and_cancelled_payments(self):
        revenue = self._analytics()['verified_revenue']

        self.assertEqual(revenue['primary'], 'INR 3,500.00')
        self.assertEqual(len(revenue['breakdown']), 1)
        self.assertEqual(revenue['breakdown'][0]['currency'], 'INR')
        self.assertEqual(revenue['breakdown'][0]['amount'], 3500.0)
        self.assertFalse(revenue['is_empty'])

        # Pending, failed, unpaid, legacy and cancelled records must not add revenue.
        self.assertNotIn('INR 4,500.00', revenue['displays'])
        self.assertNotIn('INR 1,000.00', revenue['displays'])

    def test_pending_payments_are_not_counted_as_confirmed(self):
        analytics = self._analytics()

        self.assertEqual(analytics['kpis']['pending_payments'], 3)
        self.assertEqual(analytics['kpis']['confirmed_bookings'], 3)
        self.assertEqual(analytics['verified_revenue']['primary'], 'INR 3,500.00')

    # ------------------------------------------------------------------
    # Operational insights
    # ------------------------------------------------------------------
    def test_operational_insights(self):
        insights = self._analytics()['insights']

        self.assertEqual(insights['upcoming_count'], 3)
        self.assertEqual(
            [trek.trek_name for trek in insights['upcoming_treks']],
            ['Full Capacity', 'Alpine Ridge', 'Forest Trail'],
        )

        self.assertEqual(insights['low_capacity_count'], 2)
        self.assertEqual(
            [trek.trek_name for trek in insights['low_capacity_treks']],
            ['Full Capacity', 'Alpine Ridge'],
        )

        self.assertEqual(insights['unassigned_count'], 1)
        self.assertEqual(
            [trek.trek_name for trek in insights['unassigned_treks']],
            ['Forest Trail'],
        )

        self.assertEqual(insights['pending_count'], 3)
        self.assertEqual(
            [booking.razorpay_order_id for booking in insights['pending_bookings']],
            [None, 'order_failed', 'order_pending'],
        )

    # ------------------------------------------------------------------
    # Empty database
    # ------------------------------------------------------------------
    def test_empty_database_behavior(self):
        with self.app.app_context():
            Booking.query.delete()
            Trek.query.delete()
            db.session.commit()
            analytics = build_dashboard_analytics(today=self.today)

        self.assertEqual(analytics['kpis']['total_bookings'], 0)
        self.assertEqual(analytics['kpis']['confirmed_bookings'], 0)
        self.assertEqual(analytics['kpis']['upcoming_expeditions'], 0)
        self.assertEqual(analytics['kpis']['pending_payments'], 0)
        self.assertEqual(analytics['verified_revenue']['primary'], 'INR 0.00')
        self.assertTrue(analytics['verified_revenue']['is_empty'])
        self.assertEqual(analytics['booking_status']['total'], 0)
        self.assertEqual(analytics['popular_treks'], [])
        self.assertEqual(analytics['booking_trend']['total'], 0)
        self.assertEqual(len(analytics['booking_trend']['values']), 30)
        self.assertEqual(analytics['insights']['upcoming_count'], 0)
        self.assertEqual(analytics['insights']['pending_count'], 0)

        self._login(self.admin_email)
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'No bookings yet', resp.data)
        self.assertIn(b'No non-cancelled bookings yet', resp.data)
        self.assertIn(b'INR 0.00', resp.data)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def test_dashboard_renders_analytics_charts_and_metric_labels(self):
        self._login(self.admin_email)
        resp = self.client.get('/admin/dashboard')

        self.assertEqual(resp.status_code, 200)
        for label in (
            b'Total Bookings', b'Confirmed Bookings', b'Upcoming Expeditions',
            b'Verified Revenue', b'Pending Payments', b'Booking Trends',
            b'Booking Status', b'Most Popular Treks', b'Operational Insights',
            b'Upcoming Departures', b'Low Remaining Capacity',
            b'Awaiting Payment', b'Treks Without a Guide',
        ):
            self.assertIn(label, resp.data)

        self.assertIn(b'bookingTrendChart', resp.data)
        self.assertIn(b'bookingStatusChart', resp.data)
        self.assertIn(b'popularTreksChart', resp.data)
        self.assertIn(b'chart.umd.min.js', resp.data)
        self.assertIn(b'INR 3,500.00', resp.data)

        # No customer contact details or payment secrets in analytics markup.
        self.assertNotIn(b'user1@test.com', resp.data)
        self.assertNotIn(b'user2@test.com', resp.data)
        self.assertNotIn(b'razorpay_signature', resp.data)
        self.assertNotIn(b'order_verified_active', resp.data)


if __name__ == '__main__':
    unittest.main()
