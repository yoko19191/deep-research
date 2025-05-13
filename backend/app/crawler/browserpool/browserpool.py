"""
Browser Pool Module.

This module provides classes for managing browser instances using Playwright.
It implements a pool pattern to efficiently reuse browser instances for web crawling.
"""

from playwright.async_api import async_playwright 
from asyncio import Queue, Semaphore 
from contextlib import asynccontextmanager
import atexit 
import asyncio 

from core import load_config

# Default configuration if none is provided
default_config = {
        'CRAWLER': {
            'headless': True
        }
    }

# Load configuration or use default
CONFIG = load_config(default_config) or default_config


class BrowserPlaywright:
    """
    A wrapper class for Playwright browser instance.
    
    This class manages the lifecycle of a Playwright browser instance,
    providing async context management for proper resource handling.
    
    Attributes:
        playwright: The Playwright instance.
        browser: The browser instance.
        headless (bool): Whether to run the browser in headless mode.
    """
    
    def __init__(self): 
        """Initialize a new BrowserPlaywright instance."""
        self.playwright = None 
        self.browser = None 
        self.headless = CONFIG['CRAWLER']['headless'] 
        
    async def __aenter__(self):
        """
        Async context manager entry point.
        
        Initializes playwright and browser if they don't exist.
        
        Returns:
            BrowserPlaywright: The initialized instance.
        """
        # Initialize playwright and browser once
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
        if not self.browser:
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
    
        return self 
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        """
        Async context manager exit point.
        
        Closes browser and playwright instances.
        
        Args:
            exc_type: Exception type if an exception was raised.
            exc_value: Exception value if an exception was raised.
            traceback: Traceback if an exception was raised.
        """
        # Close browser and playwright once
        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            
            
    async def new_page(self):
        """
        Create a new browser page.
        
        Returns:
            Page: A new Playwright page instance.
        """
        # Create a new page
        context = await self.browser.new_context()
        return await context.new_page()
    

class BrowserPool:
    """
    A pool of browser instances.
    
    This class manages a pool of browser instances to be reused for web crawling,
    limiting the number of concurrent browser instances.
    
    Attributes:
        pool_size (int): Maximum number of browser instances in the pool.
        pool (Queue): Queue of idle browser instances.
        lock (Semaphore): Semaphore to control concurrency.
        browser_instances (list): List of all created browser instances.
    """
    
    def __init__(self, pool_size: int):
        """
        Initialize a new BrowserPool.
        
        Args:
            pool_size (int): Maximum number of browser instances in the pool.
        """
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)  # Stores idle crawler instances
        self.lock = Semaphore(pool_size)      # Controls concurrency
        self.browser_instances = [] 
        atexit.register(lambda: asyncio.run(self.cleanup()))  # Register cleanup function on program exit

    @asynccontextmanager
    async def get_browser(self):
        """
        Get a browser instance from the pool.
        
        This is an async context manager that provides a browser instance
        and ensures it's properly returned to the pool after use.
        
        Yields:
            BrowserPlaywright: A browser instance.
        """
        async with self.lock:
            browser_instances = await self._get_browser_instances()
            try:
                yield browser_instances
            finally:
                await self._release_browser_instances(browser_instances)
                
    async def _get_browser_instances(self):
        """
        Get a browser instance from the pool or create a new one.
        
        Returns:
            BrowserPlaywright: A browser instance.
        """
        # If pool is empty, create new instances
        if self.pool.empty():
            browser_instances = await self._create_browser_instances() 
        else:
            browser_instances = await self.pool.get()
            
        return browser_instances
    
    
    async def _create_browser_instances(self):
        """
        Create a new browser instance.
        
        Returns:
            BrowserPlaywright: A new browser instance.
        """
        browser_instances = await BrowserPlaywright().__aenter__()
        self.browser_instances.append(browser_instances)
        return browser_instances
    
    async def _release_browser_instances(self, browser_instances: BrowserPlaywright):
        """
        Release a browser instance back to the pool.
        
        Args:
            browser_instances (BrowserPlaywright): The browser instance to release.
        """
        if self.pool.qsize() < self.pool_size:
            await self.pool.put(browser_instances)
            
    async def cleanup(self):
        """
        Clean up all browser instances.
        
        This method is called when the program exits to ensure all browser
        instances are properly closed.
        """
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        print("Cleaning up all browser instance...")
        # Close all browser instances in parallel  
        await asyncio.gather(
            *(browser.__aexit__(None, None, None) for browser in self.browser_instances)
        )