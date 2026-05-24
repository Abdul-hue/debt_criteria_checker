import ast
import sys
import os
from django.core.management.base import BaseCommand
from debt_app.models import CreditorCriteria
from debt_app.helpers import _RAW_CREDITOR_ALIAS_MAP

class Command(BaseCommand):
    help = "Validate CREDITOR_ALIAS_MAP against active CreditorCriteria rows."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix case mismatches in helpers.py'
        )

    def handle(self, *args, **options):
        fix = options['fix']
        
        # 1. Load the full CREDITOR_ALIAS_MAP from helpers.py
        # Already imported: _RAW_CREDITOR_ALIAS_MAP
        
        # 2. For each value in the map (unique values only), query CreditorCriteria
        unique_values = sorted(list(set(_RAW_CREDITOR_ALIAS_MAP.values())))
        
        broken_intended_values = []
        case_mismatches = {} # intended -> correct_db_name
        ok_intended_values = []
        
        for value in unique_values:
            try:
                # Query with iexact
                row = CreditorCriteria.objects.get(creditor_name__iexact=value, is_active=True)
                if row.creditor_name != value:
                    case_mismatches[value] = row.creditor_name
                else:
                    ok_intended_values.append(value)
            except CreditorCriteria.DoesNotExist:
                broken_intended_values.append(value)
            except CreditorCriteria.MultipleObjectsReturned:
                # Should not happen due to unique=True, but we handle it
                self.stderr.write(self.style.WARNING(f"Multiple active rows found for '{value}'"))
                broken_intended_values.append(value)

        # 3, 4, 6. Record and prepare report
        broken_list = [] # (key, intended, reason)
        case_mismatch_list = [] # (key, intended, correct)
        ok_count = 0
        
        for k, v in _RAW_CREDITOR_ALIAS_MAP.items():
            if v in broken_intended_values:
                broken_list.append((k, v, "BROKEN (No active row found)"))
            elif v in case_mismatches:
                case_mismatch_list.append((k, v, case_mismatches[v]))
            else:
                ok_count += 1

        # 5. Print summary
        total_checked = len(_RAW_CREDITOR_ALIAS_MAP)
        broken_count = len(broken_list)
        mismatch_count = len(case_mismatch_list)
        
        self.stdout.write(f"Summary: {total_checked} total aliases checked | {broken_count} broken | {mismatch_count} case mismatch | {ok_count} ok")

        # 6. Print full list of broken aliases
        if broken_list:
            self.stdout.write(self.style.ERROR("\nBROKEN ALIASES:"))
            for k, v, reason in broken_list:
                self.stdout.write(f"  {k} -> {v} -> {reason}")

        if mismatch_count > 0:
            self.stdout.write(self.style.WARNING("\nCASE MISMATCHES:"))
            for k, v, correct in case_mismatch_list:
                self.stdout.write(f"  {k} -> {v} (should be: {correct})")

        # 8. Accept --fix flag
        if fix and mismatch_count > 0:
            self.apply_fix(case_mismatches)
            self.stdout.write(self.style.SUCCESS("\nFixed case mismatches in debt_app/helpers.py"))

        # 7. Exit with code 1 if any broken aliases exist
        if broken_count > 0:
            sys.exit(1)
        
        sys.exit(0)

    def apply_fix(self, case_mismatches):
        """
        Rewrite helpers.py with updated alias map values.
        Uses AST to find the dict and replaces it with a properly formatted version.
        """
        file_path = os.path.join("debt_app", "helpers.py")
        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"Could not find {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            self.stderr.write(self.style.ERROR(f"Syntax error in helpers.py: {e}"))
            return

        # Find the _RAW_CREDITOR_ALIAS_MAP assignment node
        target_node = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '_RAW_CREDITOR_ALIAS_MAP':
                        target_node = node
                        break
            if target_node:
                break
        
        if not target_node or not isinstance(target_node.value, ast.Dict):
            self.stderr.write(self.style.ERROR("Could not find _RAW_CREDITOR_ALIAS_MAP dictionary in helpers.py"))
            return

        # Generate the new dictionary string
        # We'll build it manually to ensure it looks "proper" (multi-line, indented)
        # as per the "write the dict out properly" instruction.
        dict_lines = ["{"]
        for k, v in _RAW_CREDITOR_ALIAS_MAP.items():
            new_val = case_mismatches.get(v, v)
            # Use repr() to handle escaping properly
            dict_lines.append(f"    {repr(k)}: {repr(new_val)},")
        dict_lines.append("}")
        new_dict_str = "\n".join(dict_lines)

        # Splice into the original file content
        # target_node.value is the Dict node
        # lineno and end_lineno are 1-based
        lines = content.splitlines()
        
        # We replace the range from target_node.value.lineno to target_node.value.end_lineno
        # But we need to be careful with indexing
        start_idx = target_node.value.lineno - 1
        end_idx = target_node.value.end_lineno
        
        # The first line might contain the variable name and '='
        # We want to keep everything before the '{' on the first line of the dict
        first_line = lines[start_idx]
        prefix = first_line[:first_line.find('{')]
        
        new_content_lines = lines[:start_idx]
        new_content_lines.append(prefix + new_dict_str)
        new_content_lines.extend(lines[end_idx:])
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_content_lines) + "\n")
