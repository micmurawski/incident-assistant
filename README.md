# Temat pracy magisterskiej

## Autoremediacja aplikacji mikroserwisowej z wykorzystaniem systemu wieloagentowego

Celem pracy jest stworzenie systemu wieloagentowego, który będzie monitorował aplikację mikroserwisową uruchomioną na klastrze Kubernetes.

Aplikacja wdrożona na klastrze będzie jedną z aplikacji przedstawionych w niniejszej publikacji:

[link](https://elib.dlr.de/211381/1/2024_AST_MicroService_BMK.pdf)

System wieloagentowy będzie miał dostęp do logów, metryk poszczególnych serwisów, a także do kodu źródłowego aplikacji.

Aplikacja mikroserwisowa będzie poddawana drobnym modyfikacjom lub jej infrastruktura będzie sztucznie obciążana.

Zadaniem systemu wieloagentowego będzie poprawne zdiagnozowanie przyczyny awarii na podstawie dostępnych informacji (logi, metryki, kod źródłowy), opracowanie planu remediacji oraz egzekucja tego planu w celu przywrócenia prawidłowego działania aplikacji.

---

---

### Sposób generowania awarii

W tym celu zostanie stworzona osobna aplikacja agentowa, której zadaniem będzie wprowadzanie niewielkich, losowych zmian w wybranych miejscach aplikacji, mających na celu zakłócenie pracy serwisów. Dodatkowo będzie ona mogła indukować stres infrastrukturalny — lub wykonywać obie te czynności w różnych kombinacjach.

---

### Potencjalne kierunki badawcze:

- Jak różne modele diagnozy radzą sobie z wykrywaniem problemów, planowaniem i realizacją remediacji?
- W jaki sposób różne mechanizmy podejmowania decyzji wpływają na skuteczność diagnozy?
- Jaki jest optymalny zakres odpowiedzialności agenta typu SME (Subject Matter Expert)? Ile agentów potrzeba do skutecznej diagnozy systemu?
- Jak system poradzi sobie z nietrywialnymi awariami, np. wieloma błędami jednocześnie lub dodatkowym stresem infrastruktury?

---
