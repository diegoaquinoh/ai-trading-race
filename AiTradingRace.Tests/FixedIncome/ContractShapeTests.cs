using System.Text.Json.Nodes;
using AiTradingRace.Application.FixedIncome.Contracts;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>
/// C# DTOs serialize exactly the property names of the exported JSON Schemas
/// (contracts/schemas/v1), which are generated from the Pydantic source of truth.
/// </summary>
public class ContractShapeTests
{
    public static IEnumerable<object[]> Cases() => new List<object[]>
    {
        new object[] { typeof(PortfolioStateDto), "portfolio-state", null! },
        new object[] { typeof(TransitionRequestDto), "transition-request", null! },
        new object[] { typeof(TransitionProposalDto), "transition-proposal", null! },
        new object[] { typeof(RiskPolicyDto), "risk-policy", null! },
        new object[] { typeof(ExecutionModelDto), "execution-model", null! },
        new object[] { typeof(ValuationSnapshotDto), "valuation-snapshot", null! },
        new object[] { typeof(DecisionRequestDto), "decision-request", null! },
        new object[] { typeof(StrategyResultDto), "strategy-result", null! },
        new object[] { typeof(LotDto), "portfolio-state", "Lot" },
        new object[] { typeof(PositionDto), "portfolio-state", "Position" },
        new object[] { typeof(OrderIntentDto), "portfolio-state", "OrderIntent" },
        new object[] { typeof(PendingSettlementDto), "portfolio-state", "PendingSettlement" },
        new object[] { typeof(FillDto), "transition-proposal", "Fill" },
        new object[] { typeof(CashFlowRecordDto), "transition-proposal", "CashFlowRecord" },
        new object[] { typeof(JournalDto), "transition-proposal", "Journal" },
        new object[] { typeof(JournalLineDto), "transition-proposal", "JournalLine" },
        new object[] { typeof(PolicyEvaluationDto), "transition-proposal", "PolicyEvaluation" },
        new object[] { typeof(PolicyCheckDto), "transition-proposal", "PolicyCheck" },
        new object[] { typeof(TargetWeightDto), "transition-proposal", "TargetWeight" },
        new object[] { typeof(SizedOrderDto), "transition-proposal", "SizedOrder" },
        new object[] { typeof(PositionMarkDto), "transition-proposal", "PositionMark" },
        new object[] { typeof(ReconciliationReportDto), "transition-proposal", "ReconciliationReport" },
        new object[] { typeof(MarketSnapshotRefDto), "transition-request", "MarketSnapshotRef" },
        new object[] { typeof(SnapshotRefDto), "decision-request", "SnapshotRef" },
        new object[] { typeof(MarketSnapshotPointerDto), "decision-request", "MarketSnapshotPointer" },
        new object[] { typeof(DecisionBudgetDto), "decision-request", "DecisionBudget" },
        new object[] { typeof(DecisionSessionContextDto), "decision-request", "DecisionSessionContext" },
        new object[] { typeof(CitationDto), "strategy-result", "Citation" },
        new object[] { typeof(DocumentaryClaimDto), "strategy-result", "DocumentaryClaim" },
        new object[] { typeof(NumericalFindingDto), "strategy-result", "NumericalFinding" },
        new object[] { typeof(HypothesisDto), "strategy-result", "Hypothesis" },
        new object[] { typeof(ResearchNoteDto), "strategy-result", "ResearchNote" },
        new object[] { typeof(ProposalDto), "strategy-result", "Proposal" },
        new object[] { typeof(ToolTraceDto), "strategy-result", "ToolTrace" },
        new object[] { typeof(DecisionAttemptDto), "strategy-result", "DecisionAttempt" },
        new object[] { typeof(SpecialistTaskDto), "strategy-result", "SpecialistTask" },
        new object[] { typeof(UsageSummaryDto), "strategy-result", "UsageSummary" },
        new object[] { typeof(ValidationResultDto), "strategy-result", "ValidationResult" },
        new object[] { typeof(VersionInfoDto), "strategy-result", "VersionInfo" },
    };

    [Theory]
    [MemberData(nameof(Cases))]
    public void DtoPropertyNames_MatchJsonSchema(Type dtoType, string schemaName, string? definition)
    {
        var schema = JsonNode.Parse(File.ReadAllText(FiRepo.PathOf("contracts", "schemas", "v1", $"{schemaName}.schema.json")))!;
        var target = definition is null ? schema : schema["$defs"]![definition]!;
        var expected = ((JsonObject)target["properties"]!).Select(p => p.Key).OrderBy(x => x, StringComparer.Ordinal).ToList();

        var actual = FiContract.WireOptions.GetTypeInfo(dtoType).Properties
            .Where(p => !p.IsExtensionData)
            .Select(p => p.Name)
            .OrderBy(x => x, StringComparer.Ordinal)
            .ToList();

        Assert.Equal(expected, actual);
    }

    /// <summary>Internal request DTOs without a research-engine contract model: pinned to the exported OpenAPI document.</summary>
    public static IEnumerable<object[]> InternalRequestCases() => new List<object[]>
    {
        new object[] { typeof(PerformanceRequestDto), "PerformanceRequest" },
        new object[] { typeof(PerformancePortfolioDto), "PerformancePortfolio" },
        new object[] { typeof(PerformanceValuationDto), "PerformanceValuation" },
        new object[] { typeof(PerformanceMarkDto), "PerformanceMark" },
        new object[] { typeof(PerformanceLedgerDto), "PerformanceLedger" },
        new object[] { typeof(PerformanceFillDto), "PerformanceFill" },
        new object[] { typeof(PerformanceCashFlowDto), "PerformanceCashFlow" },
        new object[] { typeof(PerformancePairDto), "PerformancePair" },
        new object[] { typeof(RiskFreeSeriesDto), "RiskFreeSeries" },
        new object[] { typeof(RiskFreeObservationDto), "RiskFreeObservation" },
        new object[] { typeof(BootstrapPolicyRequestDto), "BootstrapPolicyRequest" },
        new object[] { typeof(PaymentCalendarRequestDto), "PaymentCalendarRequest" },
    };

    [Theory]
    [MemberData(nameof(InternalRequestCases))]
    public void InternalRequestDtoPropertyNames_MatchOpenApiComponents(Type dtoType, string component)
    {
        var document = JsonNode.Parse(File.ReadAllText(FiRepo.PathOf("contracts", "openapi", "research-engine.v1.json")))!;
        var target = document["components"]!["schemas"]![component]!;
        var expected = ((JsonObject)target["properties"]!).Select(p => p.Key).OrderBy(x => x, StringComparer.Ordinal).ToList();

        var actual = FiContract.WireOptions.GetTypeInfo(dtoType).Properties
            .Where(p => !p.IsExtensionData)
            .Select(p => p.Name)
            .OrderBy(x => x, StringComparer.Ordinal)
            .ToList();

        Assert.Equal(expected, actual);
    }

    [Fact]
    public void EventHeader_CoversCommonEventFields()
    {
        var schema = JsonNode.Parse(File.ReadAllText(FiRepo.PathOf("contracts", "schemas", "v1", "transition-proposal.schema.json")))!;
        var actual = FiContract.WireOptions.GetTypeInfo(typeof(PortfolioEventDto)).Properties
            .Where(p => !p.IsExtensionData).Select(p => p.Name).ToHashSet();

        foreach (var name in new[] { "CapitalFlowEvent", "SettlementDueEvent", "ValuationMarkEvent", "OrdersSubmittedEvent" })
        {
            var properties = ((JsonObject)schema["$defs"]![name]!["properties"]!).Select(p => p.Key);
            Assert.Subset(properties.ToHashSet(), actual);
        }
    }
}
