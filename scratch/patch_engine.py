import re

def update_criteria_engine():
    with open("debt_app/criteria_engine.py", "r") as f:
        content = f.read()

    # We need to add result["passed_checks"] = [] initialization
    content = content.replace('"hard_blocks": [],\n        "flags": [],\n        "info": [],', '"passed_checks": [],\n        "hard_blocks": [],\n        "flags": [],\n        "info": [],')

    # We want a wrapper that checks if a rule passed, and adds a generic message if it did, UNLESS the rule itself appended to passed_checks.
    # So we don't have to rewrite every single rule. We can just add the wrapper.
    # What if we use a wrapper first?
    wrapper_code = """
    def execute_rule(rule_func, *args):
        rule_key = rule_func.__name__.replace('_rule_', '')
        config = rules_config.get(rule_key, {})
        if not config.get('is_active', False):
            return
            
        before_blocks = len(result['hard_blocks'])
        before_flags = len(result['flags'])
        
        try:
            rule_func(*args)
        except Exception as e:
            logger.error(f"Error in rule {rule_func.__name__}: {e}")
            
        after_blocks = len(result['hard_blocks'])
        after_flags = len(result['flags'])
        
        if after_blocks == before_blocks and after_flags == before_flags:
            # Rule passed! See if rule added its own passed_checks
            # Check if this rule_key exists in passed_checks already
            if not any(p['rule_key'] == rule_key for p in result['passed_checks']):
                # determine a simple pass message based on rule_key
                # You can customize it if needed
                result['passed_checks'].append({
                    'rule_key': rule_key,
                    'rule_name': config.get('rule_name', rule_key.replace('_', ' ').title()),
                    'message': 'Passed criteria evaluation.',
                    'creditor_specific': None
                })
"""
    # Find basic_rules execution
    old_execution = """    for rule_func in basic_rules:
        try:
            rule_func(case_data, rules_config, result)
        except Exception as e:
            logger.error(f"Error in rule {rule_func.__name__}: {e}")
    
    for rule_func in docs_rules:
        try:
            rule_func(case_data, rules_config, result, uploaded_docs)
        except Exception as e:
            logger.error(f"Error in rule {rule_func.__name__}: {e}")
    
    for rule_func in creditor_rules:
        try:
            rule_func(case_data, rules_config, result, creditor_list)
        except Exception as e:
            logger.error(f"Error in rule {rule_func.__name__}: {e}")
    
    for rule_func in docs_creditor_rules:
        try:
            rule_func(case_data, rules_config, result, uploaded_docs, creditor_list)
        except Exception as e:
            logger.error(f"Error in rule {rule_func.__name__}: {e}")"""
            
    new_execution = wrapper_code + """
    for rule_func in basic_rules:
        execute_rule(rule_func, case_data, rules_config, result)
    
    for rule_func in docs_rules:
        execute_rule(rule_func, case_data, rules_config, result, uploaded_docs)
    
    for rule_func in creditor_rules:
        execute_rule(rule_func, case_data, rules_config, result, creditor_list)
    
    for rule_func in docs_creditor_rules:
        execute_rule(rule_func, case_data, rules_config, result, uploaded_docs, creditor_list)
"""
    content = content.replace(old_execution, new_execution)

    old_watch_execution = """        for rule_func in watch_basic_rules:
            try:
                rule_func(case_data, rules_config, result)
            except Exception as e:
                logger.error(f"Error in WATCH rule {rule_func.__name__}: {e}")
        
        for rule_func in watch_docs_rules:
            try:
                rule_func(case_data, rules_config, result, uploaded_docs)
            except Exception as e:
                logger.error(f"Error in WATCH rule {rule_func.__name__}: {e}")
        
        for rule_func in watch_creditor_rules:
            try:
                rule_func(case_data, rules_config, result, creditor_list)
            except Exception as e:
                logger.error(f"Error in WATCH rule {rule_func.__name__}: {e}")"""
                
    new_watch_execution = """        for rule_func in watch_basic_rules:
            execute_rule(rule_func, case_data, rules_config, result)
        
        for rule_func in watch_docs_rules:
            execute_rule(rule_func, case_data, rules_config, result, uploaded_docs)
        
        for rule_func in watch_creditor_rules:
            execute_rule(rule_func, case_data, rules_config, result, creditor_list)"""
    content = content.replace(old_watch_execution, new_watch_execution)

    with open("debt_app/criteria_engine.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    update_criteria_engine()
