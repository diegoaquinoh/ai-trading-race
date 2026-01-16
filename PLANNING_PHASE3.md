# Phase 3 – Market Data Ingestion

> **Objectif :** Stocker des prix crypto en base en récupérant les données depuis une API externe (CoinGecko).

---

## Current State Audit (07/01/2026)

### What Already Exists ✅

| Component                       | Location                              | Status                                        |
| ------------------------------- | ------------------------------------- | --------------------------------------------- |
| `IMarketDataProvider` interface | `Application/MarketData/`             | ✅ Read-only (GetLatestCandles)               |
| `EfMarketDataProvider`          | `Infrastructure/MarketData/`          | ✅ Reads candles from DB                      |
| `InMemoryMarketDataProvider`    | `Infrastructure/MarketData/`          | ✅ In-memory fallback                         |
| `MarketAsset` entity            | `Domain/Entities/`                    | ✅ Id, Symbol, Name, QuoteCurrency, IsEnabled |
| `MarketCandle` entity           | `Domain/Entities/`                    | ✅ OHLCV data with timestamp                  |
| `TradingDbContext`              | `Infrastructure/Database/`            | ✅ Configured with seeds for BTC, ETH         |
| Initial migration               | `Infrastructure/Migrations/`          | ✅ `20251211174618_InitialCreate`             |
| DI extensions                   | `Infrastructure/DependencyInjection/` | ✅ Registers EF providers                     |

### What's Missing ❌ → Status Update (16/01/2026)

| Component                       | Required For Phase 3               | Status             |
| ------------------------------- | ---------------------------------- | ------------------ |
| External API client (CoinGecko) | Fetch live OHLC data               | ✅ Done            |
| `MarketDataIngestionService`    | Orchestrate fetch → persist        | ✅ Done            |
| Duplicate candle prevention     | Avoid re-inserting same timestamp  | ✅ Done            |
| Admin/debug endpoint            | Manual ingestion trigger           | ✅ Done            |
| **Unit/Integration tests**      | Validate ingestion flow            | ✅ Done (16 tests) |
| Configuration for API keys      | CoinGecko API rate limiting / auth | ✅ Done            |

---

## Proposed Changes

### Component 1: Application Layer

Define the contracts and DTOs for market data ingestion.

#### [NEW] [IMarketDataIngestionService.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/MarketData/IMarketDataIngestionService.cs)

```csharp
public interface IMarketDataIngestionService
{
    /// <summary>
    /// Fetches latest candles from external API and persists new ones to the database.
    /// Returns the count of newly inserted candles.
    /// </summary>
    Task<int> IngestLatestCandlesAsync(string assetSymbol, CancellationToken ct = default);

    /// <summary>
    /// Ingests candles for all enabled assets.
    /// Returns total count of newly inserted candles.
    /// </summary>
    Task<int> IngestAllAssetsAsync(CancellationToken ct = default);
}
```

#### [NEW] [IExternalMarketDataClient.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/MarketData/IExternalMarketDataClient.cs)

```csharp
public interface IExternalMarketDataClient
{
    /// <summary>
    /// Fetches OHLC candles from an external market data provider.
    /// </summary>
    Task<IReadOnlyList<ExternalCandleDto>> GetCandlesAsync(
        string coinId,
        string vsCurrency,
        int days,
        CancellationToken ct = default);
}
```

#### [NEW] [ExternalCandleDto.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Application/Common/Models/ExternalCandleDto.cs)

DTO for raw candle data from external API (before mapping to domain entity).

---

### Component 2: Infrastructure Layer – CoinGecko Client

Implement the external API client using CoinGecko's free OHLC endpoint.

#### [NEW] [CoinGeckoMarketDataClient.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/MarketData/CoinGeckoMarketDataClient.cs)

**Features:**

- Uses `HttpClient` with `IHttpClientFactory`
- Calls `GET /coins/{id}/ohlc?vs_currency=usd&days=1` (or configurable)
- Parses JSON array response `[[timestamp, open, high, low, close], ...]`
- Handles rate limiting (CoinGecko free tier: 10-30 calls/min)
- Logs successes and failures

**API Reference:** https://docs.coingecko.com/v3.0.1/reference/coins-id-ohlc

**Configuration in `appsettings.json`:**

```json
{
  "CoinGecko": {
    "BaseUrl": "https://api.coingecko.com/api/v3",
    "ApiKey": "", // Optional for free tier
    "TimeoutSeconds": 30
  }
}
```

#### [NEW] [CoinGeckoOptions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/MarketData/CoinGeckoOptions.cs)

Strongly-typed options class for configuration binding.

---

### Component 3: Infrastructure Layer – Ingestion Service

#### [NEW] [MarketDataIngestionService.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/MarketData/MarketDataIngestionService.cs)

**Responsibilities:**

1. Load enabled `MarketAsset` from DB
2. Call `IExternalMarketDataClient.GetCandlesAsync()`
3. Filter out duplicates by checking existing `TimestampUtc` for the asset
4. Insert only new `MarketCandle` records
5. Log ingestion results (inserted count, skipped count)
6. Return total count of new candles

**Duplicate Prevention Logic:**

```csharp
var existingTimestamps = await _dbContext.MarketCandles
    .Where(c => c.MarketAssetId == asset.Id)
    .Select(c => c.TimestampUtc)
    .ToHashSetAsync(ct);

var newCandles = externalCandles
    .Where(c => !existingTimestamps.Contains(c.Timestamp))
    .Select(c => MapToEntity(c, asset.Id))
    .ToList();
```

---

### Component 4: Web API – Admin Endpoint

#### [NEW] [AdminController.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/Controllers/AdminController.cs)

```csharp
[ApiController]
[Route("api/[controller]")]
public class AdminController : ControllerBase
{
    private readonly IMarketDataIngestionService _ingestionService;

    [HttpPost("ingest")]
    public async Task<IActionResult> IngestMarketData(CancellationToken ct)
    {
        var count = await _ingestionService.IngestAllAssetsAsync(ct);
        return Ok(new { insertedCandles = count });
    }

    [HttpPost("ingest/{symbol}")]
    public async Task<IActionResult> IngestAsset(string symbol, CancellationToken ct)
    {
        var count = await _ingestionService.IngestLatestCandlesAsync(symbol, ct);
        return Ok(new { symbol, insertedCandles = count });
    }
}
```

---

### Component 5: Dependency Injection Updates

#### [MODIFY] [InfrastructureServiceCollectionExtensions.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/DependencyInjection/InfrastructureServiceCollectionExtensions.cs)

Add registrations:

```csharp
// CoinGecko client
services.Configure<CoinGeckoOptions>(configuration.GetSection("CoinGecko"));
services.AddHttpClient<IExternalMarketDataClient, CoinGeckoMarketDataClient>();

// Ingestion service
services.AddScoped<IMarketDataIngestionService, MarketDataIngestionService>();
```

---

### Component 6: Configuration

#### [MODIFY] [appsettings.json](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/appsettings.json)

Add CoinGecko configuration:

```json
{
  "CoinGecko": {
    "BaseUrl": "https://api.coingecko.com/api/v3",
    "ApiKey": "",
    "TimeoutSeconds": 30,
    "DefaultDays": 1
  }
}
```

#### [MODIFY] [appsettings.Development.json](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Web/appsettings.Development.json)

Add local dev overrides if needed.

---

### Component 7: Asset Symbol Mapping

CoinGecko uses different identifiers than ticker symbols:

- BTC → `bitcoin`
- ETH → `ethereum`

#### [MODIFY] [MarketAsset.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Domain/Entities/MarketAsset.cs)

Add property for external API ID:

```csharp
public string ExternalId { get; set; } = string.Empty;  // e.g., "bitcoin", "ethereum"
```

#### [NEW] Migration for ExternalId field

Generate new migration:

```bash
dotnet ef migrations add AddMarketAssetExternalId -p AiTradingRace.Infrastructure -s AiTradingRace.Web
```

#### [MODIFY] [TradingDbContext.cs](file:///Users/diegoaquino/Projets/ai-trading-race/AiTradingRace.Infrastructure/Database/TradingDbContext.cs)

Update seeds:

```csharp
new MarketAsset { Id = btcId, Symbol = "BTC", Name = "Bitcoin", ExternalId = "bitcoin" },
new MarketAsset { Id = ethId, Symbol = "ETH", Name = "Ethereum", ExternalId = "ethereum" }
```

---

## Implementation Order

| Step | Task                                   | Files                        |
| ---- | -------------------------------------- | ---------------------------- |
| 1    | Add `ExternalId` to `MarketAsset`      | Domain, DbContext, Migration |
| 2    | Create DTOs and interfaces             | Application                  |
| 3    | Implement `CoinGeckoMarketDataClient`  | Infrastructure               |
| 4    | Implement `MarketDataIngestionService` | Infrastructure               |
| 5    | Register services in DI                | Infrastructure               |
| 6    | Add configuration                      | Web appsettings              |
| 7    | Create `AdminController`               | Web                          |
| 8    | Test manually via endpoint             | Browser/curl                 |
| 9    | (Optional) Add unit/integration tests  | Tests project                |

---

## Verification Plan

### Automated Tests

> [!IMPORTANT] > **No test project exists yet.** Create `AiTradingRace.Tests` (xUnit) for unit and integration tests.

#### Unit Tests to Create

1. **`CoinGeckoMarketDataClientTests`**

   - Mock `HttpMessageHandler` to simulate CoinGecko responses
   - Test parsing of OHLC JSON array
   - Test error handling (timeout, rate limit 429)

2. **`MarketDataIngestionServiceTests`**
   - Mock `IExternalMarketDataClient` and `TradingDbContext`
   - Test duplicate filtering logic
   - Test empty response handling

#### Integration Tests

1. **`MarketDataIngestionIntegrationTests`**
   - Use SQLite in-memory provider
   - Seed `MarketAsset` with BTC
   - Call ingestion with mocked external client
   - Assert candles inserted in DB

**Run Command:**

```bash
dotnet test AiTradingRace.Tests
```

---

### Manual Verification

> [!TIP]
> Use these steps to verify the feature works end-to-end.

#### Prerequisites

1. SQL Server running (Docker or local)
2. Connection string configured via `dotnet user-secrets` or environment variable

#### Steps

1. **Apply migrations:**

   ```bash
   cd AiTradingRace.Web
   dotnet ef database update -p ../AiTradingRace.Infrastructure
   ```

2. **Start the Web API:**

   ```bash
   cd AiTradingRace.Web
   dotnet run
   ```

3. **Trigger ingestion for all assets:**

   ```bash
   curl -X POST https://localhost:7XXX/api/admin/ingest
   ```

   Expected: `{ "insertedCandles": N }` where N > 0

4. **Trigger ingestion for specific asset:**

   ```bash
   curl -X POST https://localhost:7XXX/api/admin/ingest/BTC
   ```

   Expected: `{ "symbol": "BTC", "insertedCandles": N }`

5. **Verify candles in database:**

   ```sql
   SELECT TOP 10 ma.Symbol, mc.TimestampUtc, mc.Open, mc.Close
   FROM MarketCandles mc
   JOIN MarketAssets ma ON mc.MarketAssetId = ma.Id
   ORDER BY mc.TimestampUtc DESC;
   ```

   Expected: Recent candles with realistic OHLC values for BTC/ETH

6. **Re-run ingestion (test deduplication):**
   ```bash
   curl -X POST https://localhost:7XXX/api/admin/ingest
   ```
   Expected: `{ "insertedCandles": 0 }` (no duplicates inserted)

---

## Exit Criteria

✅ Phase 3 is complete when:

1. [x] `IExternalMarketDataClient` interface created
2. [x] `CoinGeckoMarketDataClient` implemented with proper JSON parsing
3. [x] `IMarketDataIngestionService` interface created
4. [x] `MarketDataIngestionService` implemented with duplicate prevention
5. [x] `MarketAsset.ExternalId` field added with migration
6. [x] `AdminController` with `/api/admin/ingest` endpoints
7. [x] DI registrations added
8. [x] Configuration added to appsettings
9. [x] Manual verification passes (candles appear in DB) ✅ **Verified 16/01/2026** - 86 candles (43 BTC, 43 ETH)
10. [x] Re-running ingestion does not create duplicates ✅ **Verified 16/01/2026** - Returns 0 for already-ingested assets

---

## Risks & Considerations

> [!WARNING] > **Rate Limiting:** CoinGecko free tier has strict limits (10-30 calls/min). Implement exponential backoff or respect `Retry-After` header.

> [!CAUTION] > **API Changes:** CoinGecko API may change. Pin to v3 endpoints and add error logging for unexpected responses.

### Future Improvements (out of scope for Phase 3)

- Background job for scheduled ingestion (Phase 6 - Azure Functions)
- Multiple data providers (Binance, CryptoCompare)
- Historical data backfill
- Webhook/WebSocket real-time updates
