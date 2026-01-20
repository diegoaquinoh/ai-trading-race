-- Fix missing MarketAssets table
-- This script creates only the missing MarketAssets table

USE [AiTradingRace];
GO

-- Check if table exists
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'MarketAssets')
BEGIN
    PRINT 'Creating MarketAssets table...';
    
    CREATE TABLE [MarketAssets] (
        [Id] uniqueidentifier NOT NULL,
        [Symbol] nvarchar(16) NOT NULL,
        [Name] nvarchar(128) NOT NULL,
        [QuoteCurrency] nvarchar(16) NOT NULL,
        [ExternalId] nvarchar(64) NOT NULL,
        [IsEnabled] bit NOT NULL DEFAULT CAST(1 AS bit),
        CONSTRAINT [PK_MarketAssets] PRIMARY KEY ([Id])
    );
    
    CREATE UNIQUE INDEX [IX_MarketAssets_Symbol] ON [MarketAssets] ([Symbol]);
    
    -- Insert seed data
    INSERT INTO [MarketAssets] ([Id], [Symbol], [Name], [QuoteCurrency], [ExternalId], [IsEnabled])
    VALUES 
        ('11111111-1111-1111-1111-111111111111', 'BTC', 'Bitcoin', 'USD', 'bitcoin', 1),
        ('22222222-2222-2222-2222-222222222222', 'ETH', 'Ethereum', 'USD', 'ethereum', 1);
    
    PRINT 'MarketAssets table created successfully!';
END
ELSE
BEGIN
    PRINT 'MarketAssets table already exists.';
END
GO

-- Verify the table was created
SELECT COUNT(*) as TableCount FROM sys.tables WHERE name = 'MarketAssets';
SELECT COUNT(*) as RecordCount FROM [MarketAssets];
GO
