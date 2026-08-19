# Avadhi Undo?

**Avadhi Undo (അവധി ഉണ്ടോ?)** is a Kerala civic-alert project designed to answer a simple question quickly: **"Is there a holiday today?"**

The first version focuses on **official holiday and closure notices**, starting with a small set of districts and expanding later to all 14 districts of Kerala.

## What is built now

- Mobile-first public dashboard in `index.html`
- District selector
- Institution selector: schools, colleges, government offices, other institutions
- Live Kerala date/time clock
- `status.json` as the public data layer
- Configurable `config.json`
- Python scraper using the official Kerala I&PRD press-release site
- Malayalam + English keyword detection
- District-specific and statewide holiday detection
- Conservative `unknown` state instead of guessing
- Telegram alert integration through `@avadhiundo`
- GitHub Actions scheduled automation

The official I&PRD site contains real examples of district education-closure notices and statewide government-office/education holidays, which is why it is the first source being integrated. citehttps://prd.kerala.gov.in/ml/pressrelease

## Architecture

```text
Official Kerala Sources
        |
        v
  scraper.py
        |
        +----> status.json ----> index.html
        |
        +----> Telegram @avadhiundo
        |
        v
 GitHub Actions
 (scheduled checks)
```

## Current scope

### Holiday / closure alerts

The system is structured to support different institution scopes rather than treating every holiday as a universal school holiday:

- Schools
- Colleges / professional colleges
- Government offices
- Other institutions

A notice can also be **statewide**, in which case it can be reflected across the enabled district views.

### Planned next modules

The data model is intentionally extensible for:

- 🌧️ Weather and rain alerts
- 🌊 Waterlogging / flood reports
- 🚌 KSRTC and private-bus disruptions
- 🚕 Taxi / transport disruptions
- ⚡ KSEB power maintenance and outages
- 💧 KWA water-supply disruptions
- 🚇 Kochi Metro / Water Metro status
- 🚧 Road closures and diversions
- 📢 Strikes and protests
- 🏛️ Civic maintenance notices
- 📍 Community-submitted local reports
- 🇮🇳 Malayalam + English interface

## Safety / accuracy principle

Avadhi Undo should not turn an unverified social-media post or ambiguous article into a confident public alert. The scraper therefore uses an **unknown** state when an official source cannot be verified. Every active holiday result should retain its official source URL.

## Automation

`.github/workflows/check.yml` runs the scraper on a morning schedule and can also be started manually from GitHub Actions. The workflow has repository write permission so it can commit changed `status.json` data.

Telegram requires the repository secret:

`TELEGRAM_BOT_TOKEN`

The channel configured for the MVP is:

`@avadhiundo`

## Roadmap

1. **MVP:** Ernakulam + official holiday detection
2. **Verification:** test real holiday notices and Telegram delivery
3. **District expansion:** all 14 Kerala districts
4. **Weather:** official rainfall / warning feeds
5. **Civic alerts:** waterlogging, power, transport and road status
6. **Community layer:** citizen reports + admin verification
7. **Public launch:** custom domain and analytics

The project starts small on purpose: make one useful thing reliable before adding the larger civic-information layer.
