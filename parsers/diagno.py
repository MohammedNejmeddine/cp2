# diagnostic.py
import re

with open("dzn_output/j1201_1.dzn") as f:
    content = f.read()

# Extraire stock_NR
stock = int(re.search(r'stock_NR\s*=\s*(\d+)', content).group(1))

# Extraire ciment
ciment_str = re.search(r'ciment\s*=\s*\[([^\]]+)\]', content).group(1)
ciment = list(map(int, ciment_str.split(',')))

total = sum(ciment)
print(f"Stock NR   : {stock}")
print(f"Total ciment : {total}")
print(f"Infaisable ? : {total > stock}")