# Temat pracy magisterskiej

## Autoremediacja aplikacji mikroserwisowej z wykorzystaniem systemu wieloagentowego

Celem pracy jest stworzenie systemu wieloagentowego, który będzie monitorował aplikację mikroserwisową uruchomioną na klastrze Kubernetes.

Aplikacja wdrożona na klastrze będzie jedną z aplikacji przedstawionych w niniejszej publikacji:

* [An Overview of Microservice-Based Systems Used for Evaluation
in Testing and Monitoring: A Systematic Mapping Study](https://elib.dlr.de/211381/1/2024_AST_MicroService_BMK.pdf)

System wieloagentowy będzie miał dostęp do logów, metryk poszczególnych serwisów, a także do kodu źródłowego aplikacji.

Aplikacja mikroserwisowa będzie poddawana drobnym modyfikacjom lub jej infrastruktura będzie sztucznie obciążana.

Zadaniem systemu wieloagentowego będzie poprawne zdiagnozowanie przyczyny awarii na podstawie dostępnych informacji (logi, metryki, kod źródłowy), opracowanie planu remediacji oraz egzekucja tego planu w celu przywrócenia prawidłowego działania aplikacji.

---

## Diagram rozwiązania

<p align="center">
<img src="./imgs/diagram-2.drawio.png">
</p>

<div align="center">

[link do diagramu](/imgs/diagram-2.drawio.png)

</div>

---

### Sposób generowania awarii

W tym celu zostanie stworzona osobna aplikacja agentowa, której zadaniem będzie wprowadzanie niewielkich, losowych zmian w wybranych miejscach aplikacji, mających na celu zakłócenie pracy serwisów. Dodatkowo będzie ona mogła indukować stres infrastrukturalny — lub wykonywać obie te czynności w różnych kombinacjach.


### Diagnoza

Agenci SME (z ang. Subject Matter Experts) mają dostęp do rozłącznych zbiorów danych – repozytoriów kodu, logów i metryk – odpowiadających konkretnym komponentom systemu. Każdy agent podczas wywołania diagnozuje swoją część systemu i wspólnie z pozostałymi agentami SME dąży do osiągnięcia konsensusu w sprawie przyczyny problemu.

Przykłady:

* **Problem z integracją:**
Agent A zauważa, że serwis A nie może się połączyć z serwisem B z powodu błędnego wywołania endpointu REST API. Pojawia się pytanie: czy błąd leży po stronie serwisu A (wywołanie) czy serwisu B (implementacja API)? Jak agenci osiągają konsensus w tej sytuacji?

* **Problem z kolejką:** 
Agent A obserwuje, że kolejka jest przepełniona – system nie nadąża z przetwarzaniem obciążenia. Z kolei Agent B sugeruje, że kolejkę należy szybciej opróżniać. Czy problem wynika z niedostatecznych zasobów kolejki, czy z niewydolności konsumenta?

### Planowanie
Agent IC (z ang. Incident Commander) odpowiada za przyjęcie wspólnej diagnozy i przygotowanie planu naprawczego – określenia kolejnych działań niezbędnych do przywrócenia prawidłowego działania systemu.

### Egzekucja
Agent IC przekazuje zadania odpowiednim agentom SME (mogą to być inne warianty agentów wyposażone w narzędzia wykonawcze) i nadzoruje ich realizację. Po wykonaniu zadań – zmianach w kodzie i infrastrukturze – uruchamiany jest proces ponownego wdrożenia. Na zakończenie sprawdzana jest skuteczność planu, np. przez uruchomienie testów automatycznych lub analizę metryk.



---

### Potencjalne kierunki badawcze:

- Jak różne modele LLM radzą sobie z wykrywaniem problemów, planowaniem i realizacją remediacji?
- W jaki sposób różne mechanizmy podejmowania decyzji wpływają na skuteczność diagnozy? - [Reliable Decision-Making for Multi-Agent LLM System](https://multiagents.org/2025_artifacts/reliable_decision_making_for_multi_agent_llm_systems.pdf)
- Czy plan powinien być wykonywany w modelu swarm czy supervisor? ([architektura supervisor](https://github.com/langchain-ai/langgraph-supervisor-py), [architektura swarm](https://github.com/langchain-ai/langgraph-swarm-py))
- Jaki jest optymalny zakres odpowiedzialności agenta typu SME (Subject Matter Expert)? Ile agentów potrzeba do skutecznej diagnozy systemu?
- Jak system poradzi sobie z nietrywialnymi awariami, np. wieloma błędami jednocześnie lub dodatkowym stresem infrastruktury?


---


### Bibliografia:
*  [Leveraging Large Language Models for the Auto-remediation of Microservice Applications: An Experimental Study](https://dl.acm.org/doi/pdf/10.1145/3663529.3663855) - publikacja która mnie zainspirowała do tematu pracy magisterskiej, 
w badaniu realizują podobną z tą różnicą, że nie wykorzystują wielu agentów, skupiają się głównie na infrastrukturze

*  [Reliable Decision-Making for Multi-Agent LLM System](https://multiagents.org/2025_artifacts/reliable_decision_making_for_multi_agent_llm_systems.pdf) - przydatna publikacja w kontekscie modelu podejmowania decyzji podczas diagnozy

*  [LLM Multi-Agent Systems: Challenges and Open Problems](https://arxiv.org/pdf/2402.03578)
