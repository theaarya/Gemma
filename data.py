import pandas as pd
df = pd.read_csv('dd.csv')

# Check for null values
null_values = df.isnull().sum()
print("Null values in each column:\n", null_values)

# Replace null values with 'Generate yourself'
df[['video', 'image', 'pdf']] = df[['video', 'image', 'pdf']].fillna('Generate yourself')

# Replace null values in 'Depth' with the median value
df['Depth'] = df['Depth'].fillna(df['Depth'].median())

# Replace null values in 'Clarity' with the mode value
df['Clarity'] = df['Clarity'].fillna(df['Clarity'].mode()[0])

#rename the columns
df = df.rename(columns={'Carats': 'Carat','Colors': 'Color','Cuts': 'Cut','Prices': 'Price'})
df.to_csv('dd_modified.csv', index=False)