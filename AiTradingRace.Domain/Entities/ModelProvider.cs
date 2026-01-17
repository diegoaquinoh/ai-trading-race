namespace AiTradingRace.Domain.Entities;

/// <summary>
/// The AI model provider used for generating trading decisions.
/// </summary>
public enum ModelProvider
{
    /// <summary>Azure OpenAI Service (GPT-4, GPT-3.5-turbo)</summary>
    AzureOpenAI,
    
    /// <summary>OpenAI API directly</summary>
    OpenAI,
    
    /// <summary>Custom ML model via Python FastAPI (Phase 5b)</summary>
    CustomML,
    
    /// <summary>Mock provider for testing</summary>
    Mock
}
