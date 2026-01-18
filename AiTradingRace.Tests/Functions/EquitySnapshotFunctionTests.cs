using AiTradingRace.Application.Equity;
using AiTradingRace.Functions.Functions;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;
using Moq;

namespace AiTradingRace.Tests.Functions;

public class EquitySnapshotFunctionTests
{
    private readonly Mock<IEquityService> _equityServiceMock;
    private readonly Mock<ILogger<EquitySnapshotFunction>> _loggerMock;
    private readonly EquitySnapshotFunction _function;

    public EquitySnapshotFunctionTests()
    {
        _equityServiceMock = new Mock<IEquityService>();
        _loggerMock = new Mock<ILogger<EquitySnapshotFunction>>();
        _function = new EquitySnapshotFunction(_equityServiceMock.Object, _loggerMock.Object);
    }

    [Fact]
    public async Task CaptureEquitySnapshots_CallsEquityService()
    {
        // Arrange
        _equityServiceMock
            .Setup(s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(5);

        var timerInfo = CreateTimerInfo();

        // Act
        await _function.CaptureEquitySnapshots(timerInfo, CancellationToken.None);

        // Assert
        _equityServiceMock.Verify(
            s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task CaptureEquitySnapshots_LogsSnapshotCount()
    {
        // Arrange
        _equityServiceMock
            .Setup(s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(3);

        var timerInfo = CreateTimerInfo();

        // Act
        await _function.CaptureEquitySnapshots(timerInfo, CancellationToken.None);

        // Assert - Verify logging occurred
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
    public async Task CaptureEquitySnapshots_WhenServiceThrows_RethrowsException()
    {
        // Arrange
        _equityServiceMock
            .Setup(s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Database connection failed"));

        var timerInfo = CreateTimerInfo();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => _function.CaptureEquitySnapshots(timerInfo, CancellationToken.None));
    }

    [Fact]
    public async Task CaptureEquitySnapshots_WithZeroAgents_Succeeds()
    {
        // Arrange
        _equityServiceMock
            .Setup(s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(0);

        var timerInfo = CreateTimerInfo();

        // Act - Should not throw
        await _function.CaptureEquitySnapshots(timerInfo, CancellationToken.None);

        // Assert
        _equityServiceMock.Verify(
            s => s.CaptureAllSnapshotsAsync(It.IsAny<CancellationToken>()),
            Times.Once);
    }

    private static TimerInfo CreateTimerInfo()
    {
        return new TimerInfo
        {
            ScheduleStatus = new ScheduleStatus
            {
                Last = DateTime.UtcNow.AddHours(-1),
                Next = DateTime.UtcNow.AddHours(1),
                LastUpdated = DateTime.UtcNow
            }
        };
    }
}
