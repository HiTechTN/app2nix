#!/usr/bin/env python3
"""Take screenshots of app2nix web UI."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import uvicorn
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from server import app

SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

FIREFOX_BIN = "/usr/bin/firefox"


def run_server():
    """Run the uvicorn server in a thread."""
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="error")


def create_driver():
    """Create headless Firefox driver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    options.binary_location = FIREFOX_BIN

    driver = webdriver.Firefox(options=options)
    driver.set_window_size(1920, 1080)
    return driver


def take_screenshot(driver, url, filename, wait_for=None):
    """Take a screenshot of a page."""
    print(f"Taking screenshot: {filename}")
    driver.get(url)

    if wait_for:
        try:
            WebDriverWait(driver, 10).until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, wait_for))
            )
        except Exception:
            pass

    time.sleep(1)

    screenshot_path = SCREENSHOTS_DIR / filename
    driver.save_screenshot(str(screenshot_path))

    crop_screenshot(screenshot_path)
    return screenshot_path


def crop_screenshot(path):
    """Crop screenshot to reasonable size."""
    try:
        img = Image.open(path)
        width, height = img.size
        if height > 2000:
            cropped = img.crop((0, 0, width, min(height, 2000)))
            cropped.save(path)
    except Exception as e:
        print(f"Warning: Could not crop {path}: {e}")


def main():
    """Take all screenshots."""
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(3)

    base_url = "http://127.0.0.1:8002"
    driver = create_driver()

    try:
        screenshots = [
            ("01-homepage.png", base_url + "/", "nav.navbar"),
            ("02-features.png", base_url + "/#features", ".card-feature"),
            ("03-formats.png", base_url + "/#formats", ".format-badge"),
            ("04-converter.png", base_url + "/#converter", ".drop-zone"),
            ("05-api-docs.png", base_url + "/#docs", "pre"),
            ("06-api-json.png", base_url + "/api", None),
        ]

        for filename, url, selector in screenshots:
            try:
                take_screenshot(driver, url, filename, selector)
            except Exception as e:
                print(f"Error taking {filename}: {e}")

    finally:
        driver.quit()

    print(f"\nScreenshots saved to: {SCREENSHOTS_DIR}")
    for f in SCREENSHOTS_DIR.glob("*.png"):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
