import pandas as pd

df = pd.read_csv('data/raw.csv')

# Step 1 - Fill Missing Values
# Fill missing age values with median
median_age = df['age'].median()
df['age'].fillna(median_age, inplace=True)

# Fill missing income values with median
median_income = df['income'].median()
df['income'].fillna(median_income, inplace=True)

# Fill missing country values with 'Unknown'
df['country'].fillna('Unknown', inplace=True)

# Step 2 - Clip Outlier Values
# Clip age values to be within [0, 100]
df['age'] = df['age'].clip(lower=0, upper=100)

# Clip income values to be within [0, 300000]
df['income'] = df['income'].clip(lower=0, upper=300000)

# Step 3 - Add Computed Column
# Create income_per_age column
# Prevent division by zero by using max(age, 1)
df['income_per_age'] = df['income'] / df['age'].apply(lambda x: max(x, 1))

# Step 4 - Preserve Row Order
# Output the cleaned data to clean.csv

df.to_csv('data/clean.csv', index=False)