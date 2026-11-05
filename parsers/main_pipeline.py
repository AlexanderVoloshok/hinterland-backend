
from parsers.restore_data.years_missed import restore_missing_data
from parsers.restore_data.low_years import evaluate_data_completeness




# Посмотреть пропуски без запуска браузера:
#data = restore_missing_data(airports=None, match_only=True)
#print("=======DATA=======")
#print(data)

# Запустить восстановление с подтверждением сохранения
report = restore_missing_data(airports=None,  manual_accept=True)
for c in report['delete_candidates']:
    print(c)

# Поиск провалов на 1–3 года и дополнение JSON без потери прежних записей.
#found = evaluate_data_completeness(city="*", drop_fraction=0.5)