from app.core.db import db_connection
import pandas as pd

def get_test_endpoint():
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT name, email FROM users LIMIT 10")
        result = cursor.fetchall()
        cursor.close()

    df = pd.DataFrame(result, columns=["name", "email"])
    na = df.isna().sum().sum()
    
    return f"Total NA values: {na}"