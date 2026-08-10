from __future__ import annotations

import unittest

from src.data_processing.download_nasa_randomized import RANDOMIZED_ARCHIVES


class DownloadNasaRandomizedTests(unittest.TestCase):
    def test_all_official_randomized_archives_have_names_urls_and_md5(self) -> None:
        self.assertEqual(len(RANDOMIZED_ARCHIVES), 7)
        for item in RANDOMIZED_ARCHIVES:
            self.assertTrue(item["name"])
            self.assertTrue(item["url"].startswith("https://zenodo.org/records/15277374/files/"))
            self.assertEqual(len(item["official_md5"]), 32)


if __name__ == "__main__":
    unittest.main()
