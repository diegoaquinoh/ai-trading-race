using System.Security.Claims;
using AiTradingRace.Application.FixedIncome;
using Microsoft.AspNetCore.Mvc;

namespace AiTradingRace.Web.Controllers.FixedIncome;

/// <summary>
/// Shared helpers for the public /api/v1 fixed income endpoints: RFC 7807 problem
/// details (spec 14.6) and mapping of research-engine failures to status codes.
/// </summary>
public abstract class FiControllerBase : ControllerBase
{
    public const string ProblemTypePrefix = "urn:ai-trading-race:fi:problem:";

    protected string Actor =>
        User?.FindFirst(ClaimTypes.Email)?.Value
        ?? User?.Identity?.Name
        ?? User?.FindFirst(ClaimTypes.NameIdentifier)?.Value
        ?? "anonymous";

    protected ObjectResult FiProblem(int status, string code, string title, string? detail = null,
        IDictionary<string, object?>? extensions = null)
    {
        var problem = new ProblemDetails
        {
            Status = status,
            Type = ProblemTypePrefix + code,
            Title = title,
            Detail = detail,
            Instance = HttpContext?.Request?.Path.Value,
        };
        problem.Extensions["code"] = code;
        if (HttpContext is not null)
        {
            problem.Extensions["traceId"] = HttpContext.TraceIdentifier;
        }

        if (extensions is not null)
        {
            foreach (var (key, value) in extensions)
            {
                problem.Extensions[key] = value;
            }
        }

        return ProblemResult(problem, status);
    }

    protected ObjectResult FiValidationProblem(int status, string title, IReadOnlyDictionary<string, string[]> errors)
    {
        var problem = new ValidationProblemDetails(errors.ToDictionary(kv => kv.Key, kv => kv.Value))
        {
            Status = status,
            Type = ProblemTypePrefix + "validation",
            Title = title,
            Instance = HttpContext?.Request?.Path.Value,
        };
        problem.Extensions["code"] = "validation";
        return ProblemResult(problem, status);
    }

    protected ObjectResult NotFoundProblem(string what) =>
        FiProblem(StatusCodes.Status404NotFound, "not_found", $"{what} was not found.");

    /// <summary>Runs a research-engine call and maps its typed failures (400/422, 404, 409, 429, 503).</summary>
    protected async Task<IActionResult> EngineCallAsync(Func<Task<IActionResult>> call)
    {
        try
        {
            return await call();
        }
        catch (ResearchEngineValidationException ex)
        {
            return FiProblem(ex.StatusCode == StatusCodes.Status400BadRequest ? 400 : 422, "engine_validation",
                "The research engine rejected the request.", EngineDetail(ex));
        }
        catch (ResearchEngineNotFoundException ex)
        {
            return FiProblem(404, "not_found", "The requested research resource was not found.", EngineDetail(ex));
        }
        catch (ResearchEngineConflictException ex)
        {
            return FiProblem(409, "engine_conflict", "The research engine reported a conflict.", EngineDetail(ex));
        }
        catch (ResearchEngineRateLimitedException ex)
        {
            if (ex.RetryAfter is { } retry && HttpContext is not null)
            {
                Response.Headers.RetryAfter = ((int)Math.Ceiling(retry.TotalSeconds)).ToString(System.Globalization.CultureInfo.InvariantCulture);
            }

            return FiProblem(429, "rate_limited", "Research engine rate or budget limit reached.", EngineDetail(ex));
        }
        catch (ResearchEngineException ex)
        {
            return FiProblem(503, "dependency_unavailable", "The research engine is unavailable.", ex.Message);
        }
    }

    private static string? EngineDetail(ResearchEngineException ex) =>
        string.IsNullOrWhiteSpace(ex.Body) ? ex.Message : $"{ex.Message} {Truncate(ex.Body!)}";

    private static string Truncate(string value) => value.Length <= 1000 ? value : value[..1000];

    private static ObjectResult ProblemResult(ProblemDetails problem, int status)
    {
        var result = new ObjectResult(problem) { StatusCode = status };
        result.ContentTypes.Add("application/problem+json");
        return result;
    }
}
