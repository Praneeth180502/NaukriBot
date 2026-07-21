import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.scrapers.naukri_scraper import NaukriScraper
from app.core.logging import logger

async def inspect_txt_chips():
    logger.info("Starting class inspection...")
    async with NaukriScraper() as scraper:
        if not scraper._logged_in:
            await scraper.login()
            
        page = await scraper._new_page()
        try:
            await page.goto(scraper.PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # Print all span.txt or elements with class containing 'txt'
            txt_elements = await page.evaluate("""
                () => {
                    const results = [];
                    const els = document.querySelectorAll('.txt');
                    for (const el of els) {
                        // Get parent class and tag
                        const parent = el.parentElement;
                        results.push({
                            tagName: el.tagName,
                            className: el.className,
                            parentTagName: parent ? parent.tagName : '',
                            parentClassName: parent ? parent.className : '',
                            parentText: parent ? parent.textContent.trim().substring(0, 100) : '',
                            text: el.textContent.trim()
                        });
                    }
                    return results;
                }
            """)
            logger.info(f"All '.txt' elements: {txt_elements}")
            
            # Let's inspect some details from the left side links
            links = await page.evaluate("""
                () => {
                    const results = [];
                    const els = document.querySelectorAll('a, span');
                    for (const el of els) {
                        const text = el.textContent.trim();
                        if (text.includes('Resume') || text.includes('Employment') || text.includes('Education') || text.includes('Skills')) {
                            results.push({
                                tagName: el.tagName,
                                className: el.className,
                                text: text.substring(0, 50)
                            });
                        }
                    }
                    return results;
                }
            """)
            logger.info(f"Link-like elements: {links}")

        except Exception as e:
            logger.error(f"Error during class inspection: {e}")
        finally:
            await page.close()

if __name__ == "__main__":
    asyncio.run(inspect_txt_chips())
