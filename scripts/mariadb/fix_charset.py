#!/usr/bin/env python3

import pymysql
import argparse
import sys
import ssl
import socket
import os
from prettytable import PrettyTable

CHARSET_CHOICES = ["utf8mb3", "utf8mb4"]
COLLATION_CHOICES = ["utf8mb3_general_ci", "utf8mb4_general_ci"]

def connect_to_mysql():
    try:
        # Use the default MySQL socket for local connections
        mysql_password = os.getenv("MYSQL_PASSWORD", "")
        connection = pymysql.connect(
            user="root",  # Replace with your MySQL username
            password=mysql_password,  # Use environment variable if available
            unix_socket="/var/run/mysqld/mysqld.sock"  # Default MySQL socket on Ubuntu
        )
        return connection
    except pymysql.MySQLError as err:
        print(f"Error: {err}")
        sys.exit(1)

def get_database_charset_collation(connection, database):
    cursor = connection.cursor()
    query = (
        "SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME "
        "FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s"
    )
    cursor.execute(query, (database,))
    result = cursor.fetchone()
    cursor.close()
    if result:
        return result[1], result[2]
    else:
        print(f"Database '{database}' not found.")
        sys.exit(1)

def get_tables_charset_collation(connection, database):
    cursor = connection.cursor()
    query = (
        "SELECT TABLE_NAME, TABLE_COLLATION "
        "FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s"
    )
    cursor.execute(query, (database,))
    results = cursor.fetchall()
    cursor.close()
    return results

def print_charset_collation(connection, database):
    # Print current database charset and collation
    current_charset, current_collation = get_database_charset_collation(connection, database)
    print(f"Database charset: {current_charset}, collation: {current_collation}\n")

    # Create a table for displaying table charset and collation
    table = PrettyTable()
    table.field_names = ["Table Name", "Charset", "Collation", "Same as Database?"]
    table.align = "l"  # Left-align all columns

    tables = get_tables_charset_collation(connection, database)
    for table_name, table_collation in tables:
        charset = table_collation.split('_')[0] if table_collation else "Unknown"
        same_as_database = "Yes" if table_collation and table_collation.startswith(current_charset) else "No"
        table.add_row([table_name, charset, table_collation, same_as_database])

    print(f"Table charset and collation:")
    print(table)

def update_charset_collation(connection, database, charset, collation, execute_queries, exclude_tables):
    cursor = connection.cursor()
    try:
        def get_all_foreign_keys():
            cursor.execute(
                f"SELECT kcu.CONSTRAINT_NAME, kcu.TABLE_NAME, kcu.COLUMN_NAME, kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME, rc.DELETE_RULE, rc.UPDATE_RULE "
                f"FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
                f"JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc "
                f"  ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME AND rc.CONSTRAINT_SCHEMA = kcu.TABLE_SCHEMA "
                f"WHERE kcu.TABLE_SCHEMA = '{database}' AND kcu.REFERENCED_TABLE_NAME IS NOT NULL;"
            )
            return cursor.fetchall()

        def drop_all_foreign_keys(foreign_keys):
            for fk in foreign_keys:
                fk_name, table_name, _, _, _ = fk
                if table_name in exclude_tables:
                    continue
                query = f"ALTER TABLE {database}.{table_name} DROP FOREIGN KEY {fk_name};"
                print(f"Executing: {query}")
                if execute_queries:
                    cursor.execute(query)

        def recreate_all_foreign_keys(foreign_keys):
            for fk in foreign_keys:
                fk_name, table_name, column_name, ref_table, ref_column, delete_rule, update_rule = fk
                if table_name in exclude_tables:
                    continue
                on_delete = f" ON DELETE {delete_rule}" if delete_rule else ""
                on_update = f" ON UPDATE {update_rule}" if update_rule else ""
                query = (
                    f"ALTER TABLE {database}.{table_name} ADD CONSTRAINT {fk_name} FOREIGN KEY ({column_name}) "
                    f"REFERENCES {ref_table} ({ref_column}){on_delete}{on_update};"
                )
                print(f"Executing: {query}")
                if execute_queries:
                    cursor.execute(query)

        # Alter the database charset and collation if charset is provided
        if charset and collation:
            db_query = f"ALTER DATABASE {database} CHARACTER SET {charset} COLLATE {collation}"
            print(f"Executing: {db_query}")
            if execute_queries:
                cursor.execute(db_query)

        # Drop all foreign keys first
        foreign_keys = get_all_foreign_keys()
        drop_all_foreign_keys(foreign_keys)

        # Update all tables in the database
        tables = get_tables_charset_collation(connection, database)
        for table, _ in tables:
            if table in exclude_tables:
                print(f"Skipping table '{table}' as it is excluded.")
                continue
            if charset and collation:
                query = f"ALTER TABLE {database}.{table} CONVERT TO CHARACTER SET {charset} COLLATE {collation}"
                print(f"Executing: {query}")
                if execute_queries:
                    cursor.execute(query)
                    print(f"Updated table '{table}' to CHARACTER SET {charset} COLLATE {collation}.")

        # Recreate all foreign keys
        recreate_all_foreign_keys(foreign_keys)

        if execute_queries:
            connection.commit()
    except pymysql.MySQLError as err:
        print(f"Error: {err}")
        if execute_queries:
            connection.rollback()
    finally:
        cursor.close()

def main():
    parser = argparse.ArgumentParser(description="Manage MySQL database charset and collation.")
    parser.add_argument("database", help="The name of the database to connect to.")
    parser.add_argument("--charset", choices=CHARSET_CHOICES, help="Set a new charset for the database and tables.")
    parser.add_argument("--collation", choices=COLLATION_CHOICES, help="Set a new collation for the database and tables.")
    parser.add_argument("--exclude-table", action="append", default=[], help="Specify a table to exclude from alteration. Can be used multiple times for multiple tables.")
    parser.add_argument("-y", action="store_true", help="Execute changes.")

    args = parser.parse_args()

    execute_queries = args.y
    exclude_tables = args.exclude_table

    connection = connect_to_mysql()
    print_charset_collation(connection, args.database)

    if args.charset and args.collation:
        if execute_queries:
            # Drop all foreign keys, alter all tables, and recreate foreign keys
            print(f"Fixing all tables in database '{args.database}'...")
        else:
            print(f"Previewing changes for all tables in database '{args.database}'...")

        update_charset_collation(connection, args.database, args.charset, args.collation, execute_queries, exclude_tables)

    connection.close()

if __name__ == "__main__":
    main()
