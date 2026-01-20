namespace AiTradingRace.Infrastructure.Agents;

/// <summary>
/// Represents the result of validating an order from an LLM response.
/// </summary>
internal record OrderValidationResult
{
    public bool IsValid { get; }
    public string? Error { get; }

    private OrderValidationResult(bool isValid, string? error)
    {
        IsValid = isValid;
        Error = error;
    }

    public static OrderValidationResult Success() => new(true, null);
    
    public static OrderValidationResult Fail(string error) => new(false, error);
}
