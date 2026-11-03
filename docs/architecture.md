# Architecture

## 1. Whole system

```mermaid
flowchart LR
    subgraph Stations["Factory stations (IoT sensor nodes)"]
        LC["Load cell + HX711<br/>per material bin"] --> SN["Ai-Thinker board<br/>Wi-Fi"]
    end

    subgraph Laptop["Laptop = edge computer"]
        MQ["Mosquitto<br/>MQTT broker"]
        subgraph Brain["agv_brain (AI)"]
            FC["Forecaster<br/>usage rate"] --> ND["Need detector<br/>creates requests"]
            ND --> SR["Safety rules<br/>stock, room, battery, blocked lines"]
            SR --> RK["ML ranker<br/>who goes first"]
            RK --> PP["Path planner<br/>turn per junction"]
            PP --> EX["Explainer<br/>reasons + what-if"]
        end
        MQ <--> Brain
    end

    subgraph Car["Car: Ai-Thinker BW20-12F-Kit"]
        WF["Wi-Fi MQTT client"] --> JC["Junction counter"]
        IR["IR sensor array"] --> LF["PID line following"] --> MD["Motor driver"]
        US["Ultrasonic"] --> OB["Obstacle stop"]
        JC --> FK["Servo fork<br/>LIFT / LOWER"]
    end

    Cloud["Cloud broker + dashboard<br/>(HiveMQ Cloud)"]

    SN -- "stock readings" --> MQ
    MQ -- "tasks, reroutes" --> WF
    WF -- "node reached, obstacle, status" --> MQ
    MQ <-- "bridge factory/#" --> Cloud
```

The AI runs **locally** on the laptop, so decisions take milliseconds and the factory keeps running without internet. The cloud mirrors all data for the dashboard and for logging.

## 2. One decision, step by step

```mermaid
flowchart TD
    A["Stock readings arrive<br/>(every few seconds)"] --> B["Forecaster updates<br/>usage rate (EWMA)"]
    B --> C{"Will a station reach its safety stock<br/>within delivery time + horizon?"}
    C -- no --> A
    C -- yes --> D["Create request<br/>material to station"]
    D --> E["Safety rules<br/>warehouse has it? room for a box?<br/>reachable? battery OK?"]
    E -- "not OK" --> F["Alert<br/>(reorder, clear obstacle, charge)"]
    E -- OK --> G["ML ranker scores every request<br/>pairwise: i before j?"]
    G --> H["Highest score goes first"]
    H --> I["Path planner: Dijkstra over (node, heading)<br/>commands per junction"]
    I --> J["Send task to car:<br/>to rack + LIFT, to station + LOWER"]
    J --> K["Car reports each node,<br/>pickup, drop, obstacles"]
    K --> L["Re-decide after every delivery<br/>or new request"]
    L --> A
```

## 3. How the ML ranker is trained

```mermaid
flowchart LR
    S["Simulator<br/>20,000 random situations<br/>random car speed 0.6x to 1.5x"] --> T["Teacher: exact optimizer<br/>tries every order"]
    T --> P["Pairs (i, j)<br/>label: is starting with i better?"]
    P --> M["Gradient-boosted trees<br/>(scikit-learn)"]
    M --> F["models/ranker.joblib"]
    F --> E["Evaluate on 1000 new situations<br/>vs optimizer and rules"]
```

Why learn from an optimizer instead of using it directly?
- The optimizer has to try every order: 7 requests is 5,040 orders, and 10 requests is 3.6 million. The ranker compares pairs, so it stays fast however many requests are waiting.
- The optimizer still runs beside the ranker for small cases. It checks every decision ("the exact optimizer agrees") and gives the "what if" explanations.
- Later, the ranker can be retrained on **real logged runs**, where no exact model of the factory exists.

## 4. Factors the AI uses

| Factor | Where it comes from |
|---|---|
| Stock left at the station | load cell |
| Usage rate | forecaster (EWMA over the readings) |
| Time until empty, time until safety level | stock ÷ rate |
| Trip time (car → rack → station, with turns, lift and drop) | path planner + calibrated car speed |
| Slack = time until empty − trip time | derived |
| Station criticality (1–3) | config |
| How long the request has waited | request time |
| What happens to the other request if this one goes first | path planner, for every pair |
| Warehouse stock, room for a box, battery, blocked lines | hard safety rules, checked before the ML |

## 5. Code map

| File | Job |
|---|---|
| `agv_brain/models.py` | data types, loading `config/materials.yaml` |
| `agv_brain/factory_map.py` | track graph, Dijkstra with turn costs, junction commands, blocked lines, re-routing |
| `agv_brain/forecaster.py` | usage rate from load-cell readings |
| `agv_brain/need_detector.py` | automatic requests from sensor data |
| `agv_brain/safety.py` | hard rules before the ML |
| `agv_brain/simulator.py` | scoring a plan; random situations |
| `agv_brain/optimizer.py` | the exact teacher |
| `agv_brain/baselines.py` | simple rules to compare against; `rollout` |
| `agv_brain/features.py` | the numbers the ML sees |
| `agv_brain/ranker.py` | the ML model |
| `agv_brain/dataset.py` | training-data generation |
| `agv_brain/explain.py` | reasons and what-if |
| `agv_brain/dispatcher.py` | puts it all together: `Dispatcher.decide()` |
