using AiTradingRace.Infrastructure.Database;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.EntityFrameworkCore.Migrations.Operations;

namespace AiTradingRace.Tests.FixedIncome;

/// <summary>The AddFixedIncomeSchema migration is additive (fi objects only) and the snapshot matches the model.</summary>
public class FixedIncomeMigrationTests
{
    private static TradingDbContext SqlServerContext() =>
        new(new DbContextOptionsBuilder<TradingDbContext>()
            .UseSqlServer("Server=localhost;Database=design-only;User Id=x;Password=y;TrustServerCertificate=True")
            .Options);

    [Fact]
    public void AddFixedIncomeSchema_TouchesOnlyTheFiSchema()
    {
        var migrationType = typeof(TradingDbContext).Assembly.GetTypes()
            .Single(t => typeof(Migration).IsAssignableFrom(t) && t.Name == "AddFixedIncomeSchema");
        var migration = (Migration)Activator.CreateInstance(migrationType)!;

        Assert.NotEmpty(migration.UpOperations);
        Assert.All(migration.UpOperations, op =>
        {
            var schema = op switch
            {
                EnsureSchemaOperation e => e.Name,
                CreateTableOperation t => t.Schema,
                CreateIndexOperation i => i.Schema,
                _ => "unexpected:" + op.GetType().Name,
            };
            Assert.Equal("fi", schema);
        });
        Assert.All(migration.DownOperations, op => Assert.Equal("fi", Assert.IsType<DropTableOperation>(op).Schema));
        Assert.Equal(20, migration.UpOperations.OfType<CreateTableOperation>().Count());
    }

    [Fact]
    public void ModelSnapshot_MatchesCurrentModel_ExceptLegacySeedTimestamps()
    {
        using var db = SqlServerContext();
        var snapshotType = typeof(TradingDbContext).Assembly.GetTypes().Single(t => typeof(ModelSnapshot).IsAssignableFrom(t));
        var snapshot = (ModelSnapshot)Activator.CreateInstance(snapshotType, nonPublic: true)!;
        IModel snapshotModel = snapshot.Model;
        if (snapshotModel is IMutableModel mutable)
        {
            snapshotModel = mutable.FinalizeModel();
        }

        snapshotModel = db.GetService<IModelRuntimeInitializer>().Initialize(snapshotModel, designTime: true, validationLogger: null);
        var current = db.GetService<IDesignTimeModel>().Model;

        var differences = db.GetService<IMigrationsModelDiffer>()
            .GetDifferences(snapshotModel.GetRelationalModel(), current.GetRelationalModel());

        // Legacy seed rows use DateTime.UtcNow, so only their CreatedAt values may differ.
        Assert.All(differences, op => Assert.IsType<UpdateDataOperation>(op));
    }
}
