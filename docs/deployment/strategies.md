# Deployment Strategies Documentation

## Overview

This document describes three deployment strategies for model updates:
- Shadow Mode
- Canary Release
- Blue-Green Deployment

---

## 1. Shadow Mode

**Description**: New model runs in parallel with production model. Only the production model's results are returned to users, but both models' outputs are logged for comparison.

**Best for**: Testing new models with minimal risk

### How it works

```
┌─────────────┐      ┌──────────────┐
│   Request   │─────▶│   Primary    │───▶ Response to User
└─────────────┘      │   Model (v1) │
                     └──────────────┘
                           │
                           ▼ (async, logged only)
                     ┌──────────────┐
                     │   Shadow     │
                     │   Model (v2) │
                     └──────────────┘
```

### Implementation

```python
from src.api.deploy_strategies import create_strategy_manager

manager = create_strategy_manager(
    strategy="shadow",
    shadow_enabled=True
)

result = manager.process_with_shadow(
    request_data=data,
    primary_fn=primary_model.predict,
    shadow_fn=shadow_model.predict
)
```

### Pros
- Zero risk to users
- Real-world performance comparison
- Can detect issues before full rollout

### Cons
- Wasted compute (running two models)
- Shadow model issues not visible to users

---

## 2. Canary Release

**Description**: Small percentage of traffic is routed to the new model while the rest continues to use the current production model.

**Best for**: Gradual rollout with real traffic testing

### How it works

```
┌─────────────┐
│   Request   │
└──────┬──────┘
       │
       ▼ (X% random sample)
┌──────────────┐     ┌──────────────┐
│    Canary    │────▶│  New Model   │
│    (X%)      │     │    (v2)     │
└──────────────┘     └──────────────┘
       │
       │ (100-X%)
       ▼
┌──────────────┐     ┌──────────────┐
│  Production  │────▶│ Old Model    │
│  (100-X%)    │     │    (v1)     │
└──────────────┘     └──────────────┘
```

### Implementation

```python
from src.api.deploy_strategies import create_strategy_manager

manager = create_strategy_manager(
    strategy="canary",
    canary_percentage=0.1  # 10% to new model
)

# Route request
model_version = manager.route_request()

# Increase canary gradually
manager.update_canary_percentage(0.2)  # 20%
manager.update_canary_percentage(0.5)  # 50%
```

### Pros
- Controlled risk exposure
- Real traffic testing
- Easy to rollback

### Cons
- Complex routing logic
- Users may see inconsistent results

---

## 3. Blue-Green Deployment

**Description**: Two identical environments run in parallel. Traffic is switched entirely from old (blue) to new (green) environment.

**Best for**: Atomic, instant switchover

### How it works

```
┌─────────────────────────────────────────────┐
│                   LOAD BALANCER             │
└─────────────────────┬───────────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
   ┌───────────┐             ┌───────────┐
   │   BLUE    │             │  GREEN    │
   │  (v1)     │             │  (v2)     │
   │  ACTIVE   │             │  STANDBY  │
   └───────────┘             └───────────┘
   
   Switch: Update LB → 0% BLUE, 100% GREEN
```

### Implementation

```python
from src.api.deploy_strategies import create_strategy_manager

manager = create_strategy_manager(
    strategy="blue_green"
)

# Test green environment
# ... verify green is healthy ...

# Atomic switch
manager.promote_model()

# Rollback if needed
manager.rollback()
```

### Pros
- Instant switchover
- Complete isolation
- Easy rollback

### Cons
- Requires double resources
- No gradual testing with real traffic

---

## Comparison

| Strategy   | Risk   | Cost   | Testing | Complexity |
|------------|--------|--------|---------|------------|
| Shadow     | Low    | High   | Silent  | Medium     |
| Canary     | Medium | Low    | Real    | Medium     |
| Blue-Green | High   | High   | None    | Low        |

---

## AWS Implementation

### Canary with ALB

Use AWS Application Load Balancer with weighted routing:

```bash
# 10% to new version
aws elbv2 modify-rule \
  --rule-arn $RULE_ARN \
  --actions \
    Type=forward,TargetGroupArn=$OLD_TG,Weight=90 \
    Type=forward,TargetGroupArn=$NEW_TG,Weight=10
```

### Shadow with Lambda

Deploy shadow Lambda alongside production:

```python
def lambda_handler(event, context):
    # Primary response
    primary_result = primary_lambda(event)
    
    # Shadow (async, no response to user)
    invoke_async(shadow_lambda, event)
    
    return primary_result
```

---

## Recommendation

For this project, **Canary** is recommended because:
1. Easy to implement with API Gateway/ALB weighted routing
2. Real traffic validation
3. Gradual rollout reduces risk
4. Simple rollback mechanism
