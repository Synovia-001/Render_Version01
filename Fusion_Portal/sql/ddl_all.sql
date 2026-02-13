/* =========================================================
   Fusion Portal - DDL (ADM schema) for database Fusion_Dashboard
   Compatible: Microsoft SQL Server / Azure SQL Database
   ========================================================= */

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'ADM')
BEGIN
    EXEC('CREATE SCHEMA ADM AUTHORIZATION dbo');
END
GO

IF OBJECT_ID('ADM.Users', 'U') IS NULL
BEGIN
    CREATE TABLE ADM.Users (
        user_id         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        username        NVARCHAR(100) NOT NULL,
        email           NVARCHAR(255) NOT NULL,
        password_hash   NVARCHAR(255) NOT NULL,
        first_name      NVARCHAR(100) NULL,
        last_name       NVARCHAR(100) NULL,
        role            NVARCHAR(50)  NOT NULL CONSTRAINT DF_ADM_Users_role DEFAULT 'User',
        is_active       BIT NOT NULL CONSTRAINT DF_ADM_Users_is_active DEFAULT 1,
        created_at      DATETIME2(0) NOT NULL CONSTRAINT DF_ADM_Users_created_at DEFAULT SYSDATETIME(),
        last_login      DATETIME2(0) NULL
    );
    CREATE UNIQUE INDEX UX_ADM_Users_username ON ADM.Users(username);
    CREATE UNIQUE INDEX UX_ADM_Users_email ON ADM.Users(email);
END
GO

IF OBJECT_ID('ADM.UserProfile', 'U') IS NULL
BEGIN
    CREATE TABLE ADM.UserProfile (
        profile_id      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id         INT NOT NULL,
        theme           NVARCHAR(50) NULL CONSTRAINT DF_ADM_UserProfile_theme DEFAULT 'light',
        default_module  NVARCHAR(100) NULL,
        landing_layout  NVARCHAR(MAX) NULL,
        kpi_preferences NVARCHAR(MAX) NULL,
        CONSTRAINT FK_ADM_UserProfile_user FOREIGN KEY (user_id) REFERENCES ADM.Users(user_id) ON DELETE CASCADE,
        CONSTRAINT CK_ADM_UserProfile_landing_json CHECK (landing_layout IS NULL OR ISJSON(landing_layout) = 1),
        CONSTRAINT CK_ADM_UserProfile_kpi_json CHECK (kpi_preferences IS NULL OR ISJSON(kpi_preferences) = 1)
    );
    CREATE UNIQUE INDEX UX_ADM_UserProfile_user_id ON ADM.UserProfile(user_id);
END
GO

IF OBJECT_ID('ADM.Modules', 'U') IS NULL
BEGIN
    CREATE TABLE ADM.Modules (
        module_id    INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        module_name  NVARCHAR(100) NOT NULL,
        module_url   NVARCHAR(500) NOT NULL,
        icon         NVARCHAR(100) NULL,
        is_active    BIT NOT NULL CONSTRAINT DF_ADM_Modules_is_active DEFAULT 1,
        created_at   DATETIME2(0) NOT NULL CONSTRAINT DF_ADM_Modules_created_at DEFAULT SYSDATETIME()
    );
    CREATE UNIQUE INDEX UX_ADM_Modules_module_name ON ADM.Modules(module_name);
END
GO

IF OBJECT_ID('ADM.UserModuleAccess', 'U') IS NULL
BEGIN
    CREATE TABLE ADM.UserModuleAccess (
        access_id   INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        user_id     INT NOT NULL,
        module_id   INT NOT NULL,
        can_view    BIT NOT NULL CONSTRAINT DF_ADM_UserModuleAccess_can_view DEFAULT 1,
        can_edit    BIT NOT NULL CONSTRAINT DF_ADM_UserModuleAccess_can_edit DEFAULT 0,
        created_at  DATETIME2(0) NOT NULL CONSTRAINT DF_ADM_UserModuleAccess_created_at DEFAULT SYSDATETIME(),
        CONSTRAINT FK_ADM_UserModuleAccess_user FOREIGN KEY (user_id) REFERENCES ADM.Users(user_id) ON DELETE CASCADE,
        CONSTRAINT FK_ADM_UserModuleAccess_module FOREIGN KEY (module_id) REFERENCES ADM.Modules(module_id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX UX_ADM_UserModuleAccess_user_module ON ADM.UserModuleAccess(user_id, module_id);
END
GO
