/* Ensure EPOS module exists and grant full access to a user (by username).
   Run in Portal DB: Fusion_Dashboard
*/
DECLARE @username NVARCHAR(100) = N'Aidan';
DECLARE @user_id INT;

SELECT @user_id = user_id FROM ADM.Users WHERE username = @username;
IF @user_id IS NULL
    THROW 50001, 'User not found in ADM.Users. Update @username.', 1;

MERGE ADM.Modules AS tgt
USING (VALUES (N'Fusion EPOS', N'/module/EPOS', N'bi bi-bag-check', 1)) AS src (module_name, module_url, icon, is_active)
ON tgt.module_name = src.module_name
WHEN NOT MATCHED BY TARGET THEN
    INSERT (module_name, module_url, icon, is_active) VALUES (src.module_name, src.module_url, src.icon, src.is_active)
WHEN MATCHED THEN
    UPDATE SET tgt.module_url = src.module_url, tgt.icon = src.icon, tgt.is_active = src.is_active;

DECLARE @module_id INT;
SELECT @module_id = module_id FROM ADM.Modules WHERE module_name = N'Fusion EPOS';

MERGE ADM.UserModuleAccess AS tgt
USING (SELECT @user_id AS user_id, @module_id AS module_id) AS src
ON tgt.user_id = src.user_id AND tgt.module_id = src.module_id
WHEN NOT MATCHED THEN
    INSERT (user_id, module_id, can_view, can_edit) VALUES (src.user_id, src.module_id, 1, 1)
WHEN MATCHED THEN
    UPDATE SET can_view = 1, can_edit = 1;

SELECT 'OK' AS status, @user_id AS user_id, @module_id AS module_id;
