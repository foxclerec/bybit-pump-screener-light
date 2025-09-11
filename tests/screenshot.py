#!/usr/bin/env python3
"""Quick screenshot utility using Playwright."""
import argparse
import asyncio
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "screenshots"


async def take_screenshot(url: str, output: str, full_page: bool = False) -> None:
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / output

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(url, wait_until="networkidle")
        await page.screenshot(path=str(output_path), full_page=full_page)
        await browser.close()

    print(f"Screenshot saved: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Take a screenshot of a page")
    parser.add_argument("url", help="URL to screenshot")
    parser.add_argument("--output", default="screenshot.png", help="Output filename")
    parser.add_argument("--full", action="store_true", help="Full page screenshot")
    args = parser.parse_args()

    asyncio.run(take_screenshot(args.url, args.output, args.full))


if __name__ == "__main__":
    main()
