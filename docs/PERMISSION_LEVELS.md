# Department Permission Levels - Implementation Guide

## Overview

A new permission level system has been implemented that allows admins to control whether departments have **READ-only** or **READ & WRITE** access to specific features in the application.

## Features with Permission Control

The following features now support read/write permission levels:

1. **General Creditors** (`general_creditors`) - CreditorCriteria management
2. **Representative Creditors** (`representative_creditors`) - Rep-specific creditor fields
3. **Global Rules** (`global_rules`) - GlobalCriteria management
4. **Councils** (`councils`) - CouncilRule management
5. **Dividends** (`dividends`) - Dividend-related criteria
6. **SFS Guidelines** (`sfs_guidelines`) - ExpenditureGuideline management

## Permission Levels

### READ (Read-Only)
- Users can **view** all data
- Users **cannot** edit, delete, or create new records
- All GET requests are allowed
- POST, PUT, DELETE requests are blocked

### WRITE (Read & Write)
- Users can **view** all data
- Users **can** edit existing records
- Users **can** delete records
- Users **can** create new records
- All HTTP methods are allowed (GET, POST, PUT, DELETE)

## Managing Permissions

### Step 1: Access the Django Admin Interface

1. Navigate to `http://localhost:5173/admin/`
2. Log in with admin credentials
3. Go to **Debt App → Department Feature Permissions**

### Step 2: View Current Permissions

You'll see a list of all department-feature combinations with their current permission levels:

```
Default → general_creditors: READ
Default → global_rules: READ
Default → councils: READ
...
Lead Generation → general_creditors: READ
Lead Generation → global_rules: READ
...
```

### Step 3: Update Permission Levels

1. Click on a permission record to edit it
2. Change the **Permission Level** dropdown from **READ** to **WRITE**
3. Click **Save**

### Example Configuration

**Default Department:**
- General Creditors: READ
- Global Rules: READ
- Councils: READ
- Dividends: READ
- SFS Guidelines: READ

**Lead Generation Department:**
- General Creditors: **WRITE**
- Global Rules: WRITE
- Councils: READ
- Dividends: **WRITE**
- SFS Guidelines: **WRITE**

## How It Works

### For Regular Users (Non-Admin)

**When viewing data (GET requests):**
- Check: Does their department have READ or WRITE permission?
- Result: User can view the data

**When trying to edit/delete/create (POST/PUT/DELETE requests):**
- Check 1: Is user an admin? → Allow
- Check 2: Does their department have WRITE permission? → Allow
- Otherwise: Block with 403 Forbidden error

### For Admin Users

- Admin users bypass all permission checks
- Admins can always view, edit, create, and delete
- Admins can also manage the permission levels themselves

## Implementation Details

### New Models

**DepartmentFeaturePermission**
- `department` (ForeignKey) - Which department
- `feature_key` (CharField) - Which feature
- `permission_level` (CharField) - READ or WRITE
- `created_at` / `updated_at` - Timestamps

### New Permission Classes

**HasWritePermission**
- Used on POST, PUT, DELETE endpoints
- Checks if department has WRITE permission
- Admin users always pass

**HasReadPermission**
- Used on GET endpoints
- Checks if department has READ or WRITE permission
- Admin users always pass

### Updated Views

All views for permission-controlled features have been updated:
- `CreditorListView` / `CreditorDetailView`
- `RulesListView` / `RulesDetailView`
- `CouncilRuleListView` / `CouncilRuleDetailView`
- `ExpenditureGuidelineListView` / `ExpenditureGuidelineDetailView`

## API Responses

### When Permission is Denied

**Status Code:** `403 Forbidden`

**Response Body:**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

## Default Configuration

When the system is first set up, all departments receive **READ** permissions for all features. Admins must manually upgrade to **WRITE** as needed.

### To Seed Permissions Again

If you need to reset permissions to defaults:

```bash
python manage.py seed_feature_permissions --reset
```

This will:
1. Delete all existing permission records
2. Create fresh READ permission records for all departments

## Testing Permissions

### Test as Lead Generation User (WRITE Access)

1. Log in as a user in the Lead Generation department
2. Navigate to General Creditors
3. Verify you can:
   - View creditors ✓
   - Edit an existing creditor ✓
   - Create a new creditor ✓
   - Delete a creditor ✓

### Test as Default User (READ Access)

1. Log in as a user in the Default department
2. Navigate to General Creditors
3. Verify you can:
   - View creditors ✓
   - Edit a creditor ✗ (403 Forbidden)
   - Create a creditor ✗ (403 Forbidden)
   - Delete a creditor ✗ (403 Forbidden)

## Troubleshooting

### Users Getting "Permission Denied" When They Should Have Access

1. Check their department assignment
   - Go to Admin → Users → User Profiles
   - Verify the user is assigned to the correct department

2. Check their department's permissions
   - Go to Admin → Department Feature Permissions
   - Verify the department has the correct permission level

### New Department Not Getting Permissions

1. Run the seed command:
   ```bash
   python manage.py seed_feature_permissions
   ```

2. Or manually create permission records in the admin interface

## Security Notes

- Permission checks happen on the **server side** - admins cannot bypass them by editing client-side code
- All write operations log the `updated_by` user
- Permissions are checked on **every request**
- Admin users are always permitted (can't be restricted)

## Future Enhancements

Potential improvements to consider:
- [ ] More granular permissions (e.g., create-only, edit-only)
- [ ] Permission templates for quick bulk assignment
- [ ] Permission change audit log
- [ ] Role-based permission groups
- [ ] Feature-specific field-level permissions

## Support

For issues or questions about permissions:
1. Check the admin interface to verify settings
2. Run `python manage.py check` to verify system configuration
3. Check server logs for permission denial reasons
4. Contact the development team for complex permission scenarios
