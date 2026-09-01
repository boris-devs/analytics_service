import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

DATA = "data"

def load(name):
    return pd.read_csv(f"{DATA}/{name}.csv", sep=";", encoding="utf-8")

projects = load("projects")
history = load("projects_history")
report = load("report")
svc_changes = load("service_changes")
svc_terms = load("service_terms")
works = load("works")

for df, cols in [
    (report, ["flight_start", "flight_end", "last_active_month", "report_generated_at"]),
    (works, ["month"]),
    (svc_changes, ["month"]),
    (history, ["month"]),
]:
    for c in cols:
        df[c] = pd.to_datetime(df[c])

works["amount"] = pd.to_numeric(works["amount"], errors="coerce").fillna(0)
works["label"] = works["label"].fillna("").str.strip().str.lower()

print("=" * 100)
print("1. УНИКАЛЬНЫЕ КЛИЕНТЫ: сколько реально, совпадает ли с отчётом")
print("=" * 100)
all_project_ids = set(projects["project_id"])
renamed_from = set(history["project_id"])
rename_map = dict(zip(history["project_id"], history["new_project_id"]))
unique_clients = set()
for pid in all_project_ids:
    if pid in rename_map:
        continue
    unique_clients.add(pid)
print(f"project_id в projects.csv: {len(all_project_ids)} -> {sorted(all_project_ids)}")
print(f"из них переименования (projects_history): {rename_map}")
print(f"реальных уникальных клиентов после схлопывания переименований: {len(unique_clients)}")
print(f"уникальных client_id в report.csv: {report['client_id'].nunique()}")
print(f"совпадает: {len(unique_clients) == report['client_id'].nunique()}")

print()
print("=" * 100)
print("2. ТАЙМЛАЙН ОТГРУЗОК ПО КАЖДОМУ project_id: месяцы, разрывы, метки")
print("=" * 100)
for pid, g in works.sort_values("month").groupby("project_id"):
    months = sorted(g["month"].dt.to_period("M").unique())
    span = pd.period_range(months[0], months[-1], freq="M")
    gaps = [str(m) for m in span if m not in months]
    labels = g.loc[g["label"] != "", ["month", "label", "amount"]]
    zero_no_label = g[(g["amount"] == 0) & (g["label"] == "")]
    print(f"\nproject_id={pid} | месяцев с отгрузкой: {len(months)} "
          f"({months[0]}..{months[-1]}) | разрывы внутри диапазона: {gaps if gaps else 'нет'}")
    if not labels.empty:
        for _, r in labels.iterrows():
            print(f"    метка: {r['month'].date()} label='{r['label']}' amount={r['amount']}")
    if not zero_no_label.empty:
        print(f"    !! нулевые суммы БЕЗ метки: {list(zero_no_label['month'].dt.date)}")

print()
print("=" * 100)
print("3. ДЕЙСТВОВАВШИЙ service_type НА КАЖДЫЙ ФЛАЙТ report.csv (по service_changes.csv)")
print("=" * 100)
def service_at(project_id_list, month):
    changes = svc_changes[svc_changes["project_id"].isin(project_id_list)].sort_values("month")
    base_pid = project_id_list[-1]
    base = projects[projects["project_id"] == base_pid].iloc[0]
    svc, term = base["service_type"], base["term_months"]
    for _, ch in changes.iterrows():
        if month >= ch["month"]:
            svc, term = ch["new_service_type"], svc_terms.set_index("service_type").loc[ch["new_service_type"], "term_months"]
        else:
            svc, term = ch["old_service_type"], svc_terms.set_index("service_type").loc[ch["old_service_type"], "term_months"]
            break
    return svc, term

for _, row in report.iterrows():
    pids = [int(x) for x in str(row["project_ids"]).split("|")]
    svc, term = service_at(pids, row["flight_start"])
    mismatch = "  <-- НЕСОВПАДЕНИЕ" if (svc != row["service_type"] or term != row["term_months"]) else ""
    print(f"client={row['client_id']} flight_no={row['flight_no']} start={row['flight_start'].date()} "
          f"| report: {row['service_type']}/{row['term_months']} | по данным на эту дату: {svc}/{term}{mismatch}")

print()
print("=" * 100)
print("4. ПРОВЕРКА last_active_month / flight_end И flight_no ПО КАЖДОЙ СТРОКЕ ОТЧЁТА")
print("=" * 100)
for _, row in report.iterrows():
    pids = [int(x) for x in str(row["project_ids"]).split("|")]
    w = works[works["project_id"].isin(pids)]
    w = w[(w["month"] >= row["flight_start"]) & (w["month"] <= row["flight_end"])]
    real_last_active = w[w["amount"] > 0]["month"].max()
    flag = ""
    if pd.notna(real_last_active) and real_last_active != row["last_active_month"]:
        flag = "  <-- last_active_month в отчёте не совпадает с фактом внутри окна флайта"
    print(f"client={row['client_id']} flight_no={row['flight_no']} "
          f"[{row['flight_start'].date()}..{row['flight_end'].date()}] "
          f"report.last_active={row['last_active_month'].date()} "
          f"факт.last_active(в окне)={real_last_active.date() if pd.notna(real_last_active) else None}{flag}")

print()
dup = report.groupby("client_id")["flight_no"].apply(lambda s: s.duplicated().any())
print("Клиенты с задублированным flight_no:", list(dup[dup].index) if dup.any() else "нет")

print()
print("=" * 100)
print("5. ПЕРЕСЕЧЕНИЯ ОТГРУЗОК МЕЖДУ 'СТАРЫМ' И 'НОВЫМ' project_id ПОСЛЕ ПЕРЕИМЕНОВАНИЯ")
print("=" * 100)
for _, h in history.iterrows():
    old_months = set(works[works["project_id"] == h["project_id"]]["month"])
    new_months = set(works[works["project_id"] == h["new_project_id"]]["month"])
    overlap = sorted(old_months & new_months)
    print(f"{h['project_id']} -> {h['new_project_id']} (дата переименования {h['month'].date()}): "
          f"пересекающиеся месяцы отгрузок = {[m.date() for m in overlap] if overlap else 'нет'}")
