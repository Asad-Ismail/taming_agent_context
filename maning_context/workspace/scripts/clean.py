import pandas as pd

def clean_data():
    # Read the raw data
    df = pd.read_csv('data/raw.csv')

    # Step 1 - Fill Missing Values
    df['age'].fillna(df['age'].median(), inplace=True)
    df['income'].fillna(df['income'].median(), inplace=True)
    df['country'].fillna('Unknown', inplace=True)

    # Step 2 - Clip Outlier Values
    df['age'] = df['age'].clip(0, 100)
    df['income'] = df['income'].clip(0, 300000)

    # Step 3 - Add Computed Column
    df['income_per_age'] = df['income'] / df['age'].apply(lambda x: max(x, 1))

    # Step 4 - Preserve Row Order
    df.to_csv('data/clean.csv', index=False)

if __name__ == '__main__':
    clean_data()