using AiTradingRace.Application.MarketData;
using AiTradingRace.Functions.Functions;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Functions;

public class MarketDataFunctionTests
{
    private readonly Mock<IMarketDataIngestionService> _ingestionServiceMock;
    private readonly Mock<ILogger<MarketDataFunction>> _loggerMock;
    private readonly MarketDataFunction _function;

    public MarketDataFunctionTests()
    {
        _ingestionServiceMock = new Mock<IMarketDataIngestionService>();
        _loggerMock = new Mock<ILogger<MarketDataFunction>>();
        _function = new MarketDataFunction(_ingestionServiceMock.Object, _loggerMock.Object);
    }

    [Fact]
    public async Task IngestMarketData_CallsIngestionService()
    {
        // Arrange
        _ingestionServiceMock
            .Setup(s => s.IngestAllAssetsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(10);

        var timerInfo = CreateTimerInfo();

        // Act
        await _function.IngestMarketData(timerInfo, CancellationToken.None);

        // Assert
        _ingestionServiceMock.Verify(
            s => s.IngestAllAssetsAsync(It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task IngestMarketData_LogsInsertedCount()
    {
        // Arrange
        _ingestionServiceMock
            .Setup(s => s.IngestAllAssetsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(25);

        var timerInfo = CreateTimerInfo();

        // Act
        await _function.IngestMarketData(timerInfo, CancellationToken.None);

        // Assert - Verify logging occurred (at least called with Information level)
        _loggerMock.Verify(
            x => x.Log(
                LogLevel.Information,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((o, t) => true),
                It.IsAny<Exception>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.AtLeast(1));
    }

    [Fact]
    public async Task IngestMarketData_WhenServiceThrows_RethrowsException()
    {
        // Arrange
        _ingestionServiceMock
            .Setup(s => s.IngestAllAssetsAsync(It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("API Error"));

        var timerInfo = CreateTimerInfo();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _function.IngestMarketData(timerInfo, CancellationToken.None));
    }

    [Fact]
    public async Task IngestMarketData_RespectsCancellationToken()
    {
        // Arrange
        var cts = new CancellationTokenSource();
        cts.Cancel();

        _ingestionServiceMock
            .Setup(s => s.IngestAllAssetsAsync(It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException());

        var timerInfo = CreateTimerInfo();

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => _function.IngestMarketData(timerInfo, cts.Token));
    }

    private static TimerInfo CreateTimerInfo()
    {
        return new TimerInfo
        {
            ScheduleStatus = new ScheduleStatus
            {
                Last = DateTime.UtcNow.AddMinutes(-15),
                Next = DateTime.UtcNow.AddMinutes(15),
                LastUpdated = DateTime.UtcNow
            }
        };
    }
}
