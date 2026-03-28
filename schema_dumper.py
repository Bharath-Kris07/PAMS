import sqlalchemy
from sqlalchemy import create_engine, inspect

engine = create_engine('mysql+mysqlconnector://root:@localhost/pams_db')
inspector = inspect(engine)

for table_name in inspector.get_table_names():
    print(f"Table: {table_name}")
    for column in inspector.get_columns(table_name):
        print(f"  Column: {column['name']} - {column['type']} (Primary Key: {column.get('primary_key', False)}, Nullable: {column.get('nullable', True)})")
    
    for fk in inspector.get_foreign_keys(table_name):
        print(f"  FK: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
    print("-" * 40)
