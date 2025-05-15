"""
Bing Search Engine Module.

This module provides a class for performing searches on Bing and parsing the results.
It uses a browser pool to manage browser instances efficiently.
"""

from bs4 import BeautifulSoup
from app.crawler.browserpool import BrowserPool, BrowserPlaywright
from typing import Optional, List, Dict
import unicodedata
import logging
import asyncio
from app.core import load_config

# Get module logger that inherits from the root logger
logger = logging.getLogger(__name__)

# Default configuration
default_config = {
    'bing_search': {
        'base_url': 'https://cn.bing.com',
        'input_selector': 'input#sb_form_q',
        'results_selector': 'li.b_algo',
        'wait_time': 500,  # milliseconds
        'result_wait_time': 2000,  # milliseconds
        'timeout': 10000    # milliseconds
    }
}

# Load configuration or use default
CONFIG = load_config(default_config) or default_config


class BingSearch:
    """
    A class for performing searches on Bing and parsing the results.
    
    This class uses a browser pool to manage browser instances and provides
    methods for executing searches and parsing the results.
    
    Attributes:
        browser_pool (BrowserPool): The pool of browser instances to use.
        base_url (str): The base URL for Bing search.
        config (dict): Configuration parameters for the search.
    """

    def __init__(self, browser_pool: BrowserPool):
        """
        Initialize a new BingSearch instance.
        
        Args:
            browser_pool (BrowserPool): The pool of browser instances to use.
        """
        self.browser_pool = browser_pool
        self.config = CONFIG['bing_search']
        self.base_url = self.config['base_url']
        logger.info("BingSearch initialized with base URL: %s", self.base_url)

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
        context = await browser.browser.new_context()
        page = await context.new_page()
        
        try:
            # Navigate to the search page
            logger.debug("Navigating to %s", self.base_url)
            await page.goto(self.base_url, timeout=self.config['timeout'])
            
            # Fill in the search query
            logger.debug("Entering search query: %s", question)
            await page.fill(self.config['input_selector'], question)
            await page.wait_for_timeout(self.config['wait_time'])
            
            # Submit the search
            logger.debug("Submitting search query")
            await page.keyboard.press('Enter')
            
            # Wait for results to load
            logger.debug("Waiting for search results")
            await page.wait_for_selector(self.config['results_selector'], timeout=self.config['timeout'])
            await page.wait_for_timeout(self.config['result_wait_time'])
            
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
            logger.debug("Closing browser page and context")
            await page.close()
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
            items = soup.find_all("li", class_=lambda x: x and "b_algo" in x)
            
            if not items:
                logger.warning("No search result containers found in HTML")
                return None
                
            logger.debug("Found %d search result containers", len(items))
            results = []
            
            for item in items:
                try:
                    # Extract publisher and URL
                    publisher_tag = item.find("a", class_="tilk")
                    if not publisher_tag:
                        logger.warning("Publisher tag not found in result item")
                        continue
                        
                    publisher = publisher_tag.get("aria-label") or ""
                    url = publisher_tag.get("href") or ""
                    
                    # Extract content and time
                    if item.find("p"):
                        content = unicodedata.normalize("NFKC", item.find("p").get_text(strip=True))
                        content_list = content.split(" · ")
                        if len(content_list) == 2:
                            time = content_list[0]
                            summary = content_list[1]
                        else:
                            time = ""
                            summary = content_list[0]
                    else:
                        time = ""
                        summary = ""
                    
                    # Extract title
                    title_tag = item.find("h2")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    data = {
                        "title": title,
                        "publisher": publisher,
                        "url": url,
                        "summary": summary,
                        "time": time
                    }
                    
                    # Only add results with a URL
                    if url:
                        results.append(data)
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
