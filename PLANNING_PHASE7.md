# Phase 7 — React Dashboard

**Objective:** Build a modern, interactive dashboard to visualize the "race" between AI trading agents.

## 📋 Current State (Partial)

### Already Implemented (Session 07/01/2026)

| Component         | File                        | Status                                             |
| ----------------- | --------------------------- | -------------------------------------------------- |
| Project Setup     | `ai-trading-race-web/`      | ✅ Vite + React 18 + TypeScript                    |
| Types             | `src/types/index.ts`        | ✅ Base interfaces (Agent, Trade, Equity...)       |
| API Client        | `src/services/api.ts`       | ✅ Axios config, agents/equity/trades endpoints    |
| React Query Hooks | `src/hooks/useApi.ts`       | ✅ useAgents, useEquity, useTrades, useLeaderboard |
| Dashboard Page    | `src/pages/Dashboard.tsx`   | ⚠️ Basic structure, empty chart                    |
| Agent Detail Page | `src/pages/AgentDetail.tsx` | ⚠️ Basic structure, needs polish                   |
| Styling           | `src/App.css`               | ⚠️ Basic dark theme                                |
| CORS Backend      | `Program.cs`                | ✅ Configured for localhost:5173                   |

### Identified Gaps

1. **Dashboard**: Multi-agent chart is empty (placeholder only)
2. ~~**Endpoint `/api/leaderboard`**: Does not exist in backend yet~~ ✅ Created
3. **General Layout**: No sidebar/topbar
4. **Design**: Basic styling, lacks animations and modern effects
5. **UI Components**: No reusable components
6. **Real-time Data**: Polling configured but not tested with backend
7. **Page `/agents`**: Not implemented (only `/` and `/agents/:id`)

---

## 🎯 Phase 7 Deliverables

### 1. Layout & Navigation ✅ Sprint 7.2 Complete

- [x] **1.1** Create fixed Header/Topbar with logo and navigation
- [x] **1.2** Create responsive Sidebar with Dashboard/Agents links
- [x] **1.3** Add minimal Footer with last update status
- [ ] **1.4** Implement mobile adaptation (responsive design)

### 2. Dashboard Page (`/`) ✅ Sprint 7.3 Complete

- [x] **2.1** Build interactive Leaderboard with sorting and filtering
- [x] **2.2** Implement multi-agent EquityChart with Recharts (overlaid curves)
- [x] **2.3** Create StatCards (best agent, worst agent, total volume)
- [x] **2.4** Add market indicators (latest BTC/ETH prices)
- [x] **2.5** Configure auto-refresh with visual indicator

### 3. Agents List Page (`/agents`)

- [ ] **3.1** Create full agents list with pagination
- [ ] **3.2** Add filters by type (LLM/CustomML), status (active/inactive)
- [ ] **3.3** Add mini sparklines showing equity trend for each agent
- [ ] **3.4** Implement quick actions (view detail, start/stop if admin)

### 4. Agent Detail Page (`/agents/:id`)

- [ ] **4.1** Display key metrics: Total value, % performance, max drawdown, Sharpe ratio
- [ ] **4.2** Build equity chart with period selection (1D, 7D, 30D, ALL)
- [ ] **4.3** Show current positions with % of portfolio
- [ ] **4.4** Create paginated trade history with filters (BUY/SELL)
- [ ] **4.5** Display agent info: strategy, provider, creation date

### 5. Reusable Components (Partial - Core done)

- [x] **5.1** `<EquityChart>` — Configurable equity chart component
- [x] **5.2** `<LeaderboardTable>` — Ranked table component
- [ ] **5.3** `<TradeHistory>` — Paginated trade list component
- [ ] **5.4** `<PositionCard>` — Position display with PnL
- [x] **5.5** `<StatCard>` — Animated statistic card
- [ ] **5.6** `<LoadingSpinner>` — Loading indicator
- [ ] **5.7** `<ErrorMessage>` — Formatted error message
- [ ] **5.8** `<EmptyState>` — Empty state with illustration

### 6. Design System

- [ ] **6.1** Define CSS variables for colors, spacing, typography
- [ ] **6.2** Finalize dark theme (already started)
- [ ] **6.3** Add CSS animations for transitions and hover effects
- [ ] **6.4** Assign unique colors per agent for chart differentiation
- [ ] **6.5** Configure modern typography (Inter or Roboto from Google Fonts)

### 7. Backend API Additions ✅ Sprint 7.1 Complete

- [x] **7.1** Create `GET /api/leaderboard` — Dedicated leaderboard endpoint
- [x] **7.2** Create `GET /api/market/prices` — Latest prices for header display
- [x] **7.3** Verify DTO compatibility with frontend types

---

## 🏗️ Frontend Architecture

```
ai-trading-race-web/
├── src/
│   ├── components/       # Reusable components
│   │   ├── charts/       # EquityChart, SparkLine
│   │   ├── common/       # StatCard, Button, Modal
│   │   └── layout/       # Header, Sidebar, Footer
│   ├── pages/            # Main pages
│   │   ├── Dashboard.tsx
│   │   ├── AgentList.tsx
│   │   └── AgentDetail.tsx
│   ├── hooks/            # Custom hooks
│   ├── services/         # API clients
│   ├── types/            # TypeScript types
│   ├── styles/           # CSS modules or style files
│   │   ├── variables.css
│   │   └── animations.css
│   └── utils/            # Utility functions
├── public/
└── index.html
```

---

## 🛠️ Tech Stack

| Category      | Technology              | Version |
| ------------- | ----------------------- | ------- |
| Framework     | React                   | 18.x    |
| Build         | Vite                    | 5.x     |
| Language      | TypeScript              | 5.x     |
| Routing       | react-router-dom        | 6.x     |
| Data Fetching | @tanstack/react-query   | 5.x     |
| HTTP Client   | Axios                   | 1.x     |
| Charts        | Recharts                | 2.x     |
| Styling       | Vanilla CSS (variables) | -       |

---

## 📅 Execution Plan

### Sprint 7.1 — Backend Support (0.5 day) ✅ Complete

| #   | Task                                     | Status |
| --- | ---------------------------------------- | ------ |
| 7.1 | Create `GET /api/leaderboard` endpoint   | [x]    |
| 7.2 | Create `GET /api/market/prices` endpoint | [x]    |
| 7.3 | Verify existing DTOs                     | [x]    |

### Sprint 7.2 — Layout & Design System (1 day) ✅ Complete

| #   | Task                                      | Status |
| --- | ----------------------------------------- | ------ |
| 6.1 | Implement CSS variables and design tokens | [x]    |
| 1.1 | Create Header component                   | [x]    |
| 1.2 | Create Sidebar component                  | [x]    |
| 1.3 | Create Footer component                   | [x]    |
| 6.5 | Add Google Fonts (Inter)                  | [x]    |

### Sprint 7.3 — Dashboard Complete (1.5 days) ✅ Complete

| #   | Task                                     | Status |
| --- | ---------------------------------------- | ------ |
| 5.5 | Build StatCard component                 | [x]    |
| 5.2 | Build LeaderboardTable component         | [x]    |
| 2.1 | Implement Dashboard leaderboard          | [x]    |
| 5.1 | Build EquityChart component              | [x]    |
| 2.2 | Implement multi-agent chart on Dashboard | [x]    |
| 2.4 | Add market price indicators              | [x]    |
| 2.5 | Configure auto-refresh with indicator    | [x]    |

### Sprint 7.4 — Agent Pages (1.5 days) ✅ Complete

| #   | Task                                  | Status |
| --- | ------------------------------------- | ------ |
| 3.1 | Create AgentList page with pagination | [x]    |
| 3.2 | Add agent list filters                | [x]    |
| 4.1 | Display key metrics on AgentDetail    | [x]    |
| 4.2 | Add period selector to equity chart   | [x]    |
| 5.3 | Build TradeHistory component          | [x]    |
| 5.4 | Build PositionCard component          | [x]    |
| 4.3 | Show current positions                | [x]    |
| 4.4 | Implement trade history with filters  | [x]    |

### Sprint 7.5 — Polish & UX (1 day) ✅ Complete

| #   | Task                              | Status |
| --- | --------------------------------- | ------ |
| 6.3 | Add animations and transitions    | [x]    |
| 5.6 | Build LoadingSpinner component    | [x]    |
| 5.7 | Build ErrorMessage component      | [x]    |
| 5.8 | Build EmptyState component        | [x]    |
| 1.4 | Responsive design (mobile/tablet) | [x]    |

---

## ✅ Exit Criteria

| Criterion                                    | Validated |
| -------------------------------------------- | --------- |
| Dashboard displays agent leaderboard         | [x]       |
| Equity curves are overlaid on a single chart | [x]       |
| Clicking an agent navigates to detail page   | [x]       |
| Recent trades are visible with pagination    | [x]       |
| Application is responsive (mobile/desktop)   | [x]       |
| Loading/error states are handled properly    | [x]       |
| Production build passes (`npm run build`)    | [x]       |
| Application connects to .NET backend         | [x]       |

---

## 🔗 Dependencies

- **Phase 6** (Azure Functions): ✅ Completed
- **Backend API**: All `/api/agents/*`, `/api/equity/*` endpoints are available
- **Database**: Must contain data (agents, trades, snapshots) for testing

---

## 📝 Notes

- Frontend listens on `localhost:5173` (dev), backend on `localhost:5000` or `localhost:7240`
- Environment variable `VITE_API_URL` configured in `.env` or `.env.local`
- CORS credentials enabled in backend for cookie support if needed

---

## 🚀 Commands

```bash
# Start development
cd ai-trading-race-web
npm install
npm run dev

# Production build
npm run build

# Linting
npm run lint

# Backend (in another terminal)
dotnet run --project AiTradingRace.Web
```
