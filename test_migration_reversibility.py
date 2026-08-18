"""
Test migration reversibility for task 2.5
"""
import subprocess
import sys
from sqlalchemy import create_engine, inspect

def run_command(cmd):
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def check_column_exists(engine, table, column):
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table)]
    return column in columns

def check_index_exists(engine, table, index):
    """Check if an index exists on a table."""
    inspector = inspect(engine)
    indexes = [idx['name'] for idx in inspector.get_indexes(table)]
    return index in indexes

def test_migration_reversibility():
    """Test that the migration can be reversed and re-applied."""
    engine = create_engine('sqlite:///mfscope.db')
    
    print("=" * 60)
    print("Testing Migration Reversibility")
    print("=" * 60)
    
    # Check initial state
    print("\n1. Checking current state (migration applied)...")
    has_column = check_column_exists(engine, 'scheme', 'inception_date')
    has_index = check_index_exists(engine, 'scheme', 'ix_scheme_inception_date')
    
    if has_column and has_index:
        print("   ✓ Column and index exist")
    else:
        print("   ✗ Migration not in expected state")
        return False
    
    # Test downgrade
    print("\n2. Testing downgrade (removing column and index)...")
    returncode, stdout, stderr = run_command("alembic downgrade -1")
    
    if returncode == 0:
        print("   ✓ Downgrade command succeeded")
    else:
        print(f"   ✗ Downgrade failed: {stderr}")
        return False
    
    # Verify column removed
    print("\n3. Verifying column and index removed...")
    has_column = check_column_exists(engine, 'scheme', 'inception_date')
    has_index = check_index_exists(engine, 'scheme', 'ix_scheme_inception_date')
    
    if not has_column and not has_index:
        print("   ✓ Column and index successfully removed")
    else:
        print(f"   ✗ Removal failed: column={has_column}, index={has_index}")
        # Re-upgrade to restore state
        run_command("alembic upgrade head")
        return False
    
    # Test upgrade
    print("\n4. Testing upgrade (re-adding column and index)...")
    returncode, stdout, stderr = run_command("alembic upgrade head")
    
    if returncode == 0:
        print("   ✓ Upgrade command succeeded")
    else:
        print(f"   ✗ Upgrade failed: {stderr}")
        return False
    
    # Verify column re-added
    print("\n5. Verifying column and index re-added...")
    has_column = check_column_exists(engine, 'scheme', 'inception_date')
    has_index = check_index_exists(engine, 'scheme', 'ix_scheme_inception_date')
    
    if has_column and has_index:
        print("   ✓ Column and index successfully restored")
    else:
        print(f"   ✗ Restoration failed: column={has_column}, index={has_index}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ Migration Reversibility Test PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_migration_reversibility()
    sys.exit(0 if success else 1)
