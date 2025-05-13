import logging
import sys 



def setup_logger(log_level=logging.INFO):
    """Setup global logger"""
    root_logger = logging.getLogger() 
    
    root_logger.setLevel(log_level)
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        defaults='%Y-%m-%d %H:%M:%S'
        )
    console_handler.setFormatter(formatter)
    
    # add handler to root logger
    root_logger.addHandler(console_handler)
    


if __name__ == '__main__':
    setup_logger(logging.DEBUG)