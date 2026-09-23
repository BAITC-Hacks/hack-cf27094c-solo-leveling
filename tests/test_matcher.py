"Run with python -m unittest discover -s tests -v."

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from app import Handler, ThreadingHTTPServer
from catalog import CATALOG
from matcher import InvalidQuery, recommend


BASE = dict(city="Алматы", event_date="2026-10-15", event_format="свадьба",
            category="Ведущий", budget=1500000, wishes="юмор")


class MatchingTests(unittest.TestCase):
    def test_live_demo_and_repeatability(self):
        first = recommend(BASE)
        self.assertEqual(first, recommend(dict(BASE)))
        self.assertEqual(first["status"], "matched")
        self.assertEqual(len(first["cards"]), 3)
        by_id = {item.id: item for item in CATALOG}
        for card in first["cards"]:
            profile = by_id[card["id"]]
            self.assertEqual(profile.city, BASE["city"])
            self.assertIn(BASE["category"], profile.categories)
            self.assertIn(BASE["event_format"], profile.formats)
            self.assertNotIn(BASE["event_date"], profile.busy_dates)
            self.assertLessEqual(profile.price, BASE["budget"])
            self.assertIn("В описании:", card["explanation"])
            self.assertIn(BASE["event_date"], card["explanation"])

    def test_date_changes_candidates_and_explains_availability(self):
        autumn = recommend(BASE)
        following_day = recommend(dict(BASE, event_date="2026-10-16"))
        self.assertNotEqual([c["id"] for c in autumn["cards"]],
                            [c["id"] for c in following_day["cards"]])
        self.assertNotEqual(autumn["counts"]["busy"], following_day["counts"]["busy"])
        self.assertIn("заняты на дату", following_day["message"])

    def test_rare_category_and_two_distinct_empty_outcomes(self):
        rare = recommend(dict(BASE, category="Флорист", event_date="2026-11-14",
                              budget=500000, wishes=""))
        self.assertEqual(rare["status"], "matched")
        self.assertEqual(len(rare["cards"]), 1)
        self.assertIn("Меньше трёх", rare["message"])
        no_category = recommend(dict(BASE, city="Астана", category="Декоратор"))
        self.assertEqual(no_category["status"], "no_category")
        self.assertIn("нет подрядчиков", no_category["message"])
        excluded = recommend(dict(BASE, city="Астана", category="Флорист",
                                  event_date="2026-12-31", budget=500000))
        self.assertEqual(excluded["status"], "no_eligible")
        self.assertIn("заняты на дату", excluded["message"])

    def test_optional_language_hours_and_budget_are_hard_limits(self):
        result = recommend(dict(BASE, language="казахский", hours=8, budget=900000))
        by_id = {item.id: item for item in CATALOG}
        for card in result["cards"]:
            profile = by_id[card["id"]]
            self.assertIn("казахский", profile.languages)
            self.assertTrue(profile.max_hours is None or profile.max_hours >= 8)
            self.assertLessEqual(profile.price, 900000)
        self.assertEqual(result["counts"]["city_category"],
                         len(result["cards"]) + sum(result["counts"][key] for key in result["counts"] if key != "city_category"))

    def test_dates_outside_known_calendar_are_rejected(self):
        for bad_date in ("2026-09-22", "2027-01-01", "2026-02-30"):
            with self.subTest(date=bad_date), self.assertRaises(InvalidQuery):
                recommend(dict(BASE, event_date=bad_date))


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_page_metadata_and_json_endpoint(self):
        with urlopen(self.url + "/") as response:
            self.assertIn("Подрядчик под ваше событие", response.read().decode())
        with urlopen(self.url + "/api/options") as response:
            options = json.load(response)
        self.assertEqual(options["profiles"], 66)
        with urlopen(self.url + "/api/recommend?" + urlencode(BASE)) as response:
            data = json.load(response)
        self.assertEqual(data["status"], "matched")
        self.assertLessEqual(len(data["cards"]), 3)

    def test_bad_input_is_client_error(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/api/recommend?" + urlencode(dict(BASE, budget="-1")))
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
