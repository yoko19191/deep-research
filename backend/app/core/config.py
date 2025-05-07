import yaml
import os

def load_config(config_section: dict = None):
    """
    Load configuration from config.yaml file in project root directory.
    
    Args:
        config_section: Dictionary specifying which configuration sections to return,
                    e.g. {'crawler': True}. If None, returns the entire configuration.
    
    Returns:
        dict: Requested configuration if successful; None if error occurs or file not found.
    """
    # Get current file directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Search upward until finding project root (directory containing config.yaml)
    root_dir = current_dir
    while not os.path.exists(os.path.join(root_dir, 'config.yaml')):
        parent_dir = os.path.dirname(root_dir)
        if parent_dir == root_dir:  # Reached filesystem root
            return None
        root_dir = parent_dir
    
    # Config file path
    config_path = os.path.join(root_dir, 'config.yaml')
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
            # If config is empty, return None
            if not config:
                return None
                
            # If specific sections requested, return only those sections
            if config_section:
                result = {}
                for section in config_section:
                    if section in config:
                        result[section] = config[section]
                    else:
                        # Return None if any requested section is missing
                        return None
                return result
            
            # Otherwise return entire config
            return config
            
    except (FileNotFoundError, yaml.YAMLError, Exception) as e:
        print(f"Error: Failed to load config file {config_path}: {str(e)}")
        return None