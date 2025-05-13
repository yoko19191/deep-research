"""
Sougou Search Engine Module.

This module provides a class for performing searches on Sougou and parsing the results.
It uses a browser pool to manage browser instances efficiently.
"""

from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from browserpool import BrowserPool, BrowserPlaywright
import logging
import asyncio
from core import load_config

# Get module logger that inherits from the root logger
logger = logging.getLogger(__name__)

# Default configuration
default_config = {
    'sougou_search': {
        'base_url': 'https://www.sogou.com',
        'input_selector': 'input#query',
        'submit_selector': 'input#stb',
        'results_selector': 'div.vrwrap',
        'wait_time': 1000,  # milliseconds
        'timeout': 10000    # milliseconds
    }
}

# Load configuration or use default
CONFIG = load_config(default_config) or default_config


class SougouSearch:
    """
    A class for performing searches on Sougou and parsing the results.
    
    This class uses a browser pool to manage browser instances and provides
    methods for executing searches and parsing the results.
    
    Attributes:
        browser_pool (BrowserPool): The pool of browser instances to use.
        base_url (str): The base URL for Sougou search.
        config (dict): Configuration parameters for the search.
    """

    def __init__(self, browser_pool: BrowserPool):
        """
        Initialize a new SougouSearch instance.
        
        Args:
            browser_pool (BrowserPool): The pool of browser instances to use.
        """
        self.browser_pool = browser_pool
        self.config = CONFIG['sougou_search']
        self.base_url = self.config['base_url']
        logger.info("SougouSearch initialized with base URL: %s", self.base_url)

    async def response(self, questions: Optional[List[str]]) -> Optional[Dict[str, List[Dict[str, str]]]]:
        """
        Execute searches for a list of questions and return the results.
        
        Args:
            questions (Optional[List[str]]): A list of search queries.
            
        Returns:
            Optional[Dict[str, List[Dict[str, str]]]]: A dictionary mapping each question
                to a list of search results, or None if no results were found.
        """
        if not questions:
            logger.warning("No questions provided for search")
            return None
            
        results = {}
        logger.info("Processing %d search queries", len(questions))
        
        try:
            async with self.browser_pool.get_browser() as browser:
                for question in questions:
                    logger.info("Searching for: %s", question)
                    try:
                        html = await self.run(browser=browser, question=question)
                        result = self.parsing(html)
                        if result:
                            results[question] = result
                            logger.info("Found %d results for query: %s", len(result), question)
                        else:
                            logger.warning("No results found for query: %s", question)
                    except Exception as e:
                        logger.error("Error searching for '%s': %s", question, str(e))
                        # Continue with next question instead of failing completely
                        continue
        except Exception as e:
            logger.error("Failed to get browser from pool: %s", str(e))
            return None

        return results if results else None

    async def run(self, browser: BrowserPlaywright, question: Optional[str]) -> str:
        """
        Execute a search query using the provided browser instance.
        
        Args:
            browser (BrowserPlaywright): The browser instance to use.
            question (str): The search query.
            
        Returns:
            str: The HTML content of the search results page.
            
        Raises:
            TimeoutError: If the page load or search operation times out.
            Exception: For other errors during the search process.
        """
        if not question:
            logger.warning("Empty question provided for search")
            return ""
            
        logger.debug("Creating new browser context and page")
        context = None
        page = None
        
        try:
            # Create a new context with custom user agent
            context = await browser.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Navigate to the search page
            logger.debug("Navigating to %s", self.base_url)
            await page.goto(self.base_url, timeout=self.config['timeout'])
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Fill in the search query
            logger.debug("Entering search query: %s", question)
            await page.fill(self.config['input_selector'], question)
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Submit the search
            logger.debug("Submitting search query")
            await page.click(self.config['submit_selector'])
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Wait for results to load
            logger.debug("Waiting for search results")
            await page.wait_for_selector(self.config['results_selector'], timeout=self.config['timeout'])
            
            # Get the page content
            html = await page.content()
            logger.debug("Retrieved search results page content")
            return html
            
        except asyncio.TimeoutError as e:
            logger.error("Timeout while searching for '%s': %s", question, str(e))
            raise
        except Exception as e:
            logger.error("Error during search for '%s': %s", question, str(e))
            raise
        finally:
            # Always close the page and context to avoid resource leaks
            if page:
                logger.debug("Closing browser page")
                await page.close()
            if context:
                logger.debug("Closing browser context")
                await context.close()

    def parsing(self, html: Optional[str]) -> Optional[List[Dict[str, str]]]:
        """
        Parse the HTML content of a search results page.
        
        Args:
            html (Optional[str]): The HTML content to parse.
            
        Returns:
            Optional[List[Dict[str, str]]]: A list of dictionaries containing the parsed
                search results, or None if no results were found or the HTML was invalid.
        """
        if not html:
            logger.warning("Empty HTML provided for parsing")
            return None
            
        try:
            logger.debug("Parsing search results HTML")
            soup = BeautifulSoup(html, "lxml")
            items = soup.find_all("div", class_="vrwrap")
            
            if not items:
                logger.warning("No search result containers found in HTML")
                return None
                
            logger.debug("Found %d search result containers", len(items))
            results = []
            
            for item in items:
                try:
                    # Extract title and URL
                    title_tag = item.select_one("h3.vr-title a")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    url = title_tag.get("href", "") if title_tag else ""
                    
                    # Handle relative URLs
                    if url and url.startswith("/link?url="):
                        url = f"{self.base_url}{url}"
                    
                    # Extract summary
                    summary_tag = item.select_one("div.text-layout p.star-wiki")
                    if summary_tag:
                        summary = summary_tag.get_text(strip=True)
                    else:
                        alt_summary_tag = item.select_one("div.fz-mid.space-txt")
                        summary = alt_summary_tag.get_text(strip=True) if alt_summary_tag else ""
                    
                    # Extract publisher
                    publisher_tag = item.find("div", class_="citeurl")
                    publisher = publisher_tag.get_text(strip=True) if publisher_tag else ""
                    
                    # Extract time
                    time = ""
                    if summary:
                        time_parts = summary.split("-")
                        if len(time_parts) == 2:
                            time = time_parts[0].strip()
                    
                    # Only add results with title and URL
                    if title and url:
                        data = {
                            "title": title,
                            "publisher": publisher,
                            "url": url,
                            "summary": summary,
                            "time": time
                        }
                        results.append(data)
                    else:
                        logger.debug("Skipping result without title or URL")
                except Exception as e:
                    logger.warning("Error parsing search result item: %s", str(e))
                    continue
            
            if results:
                logger.info("Parsed %d search results", len(results))
                return results
            else:
                logger.warning("No valid search results found")
                return None
                
        except Exception as e:
            logger.error("Error parsing search results HTML: %s", str(e))
            return None


