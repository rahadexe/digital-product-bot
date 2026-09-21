-- Keep the newest active key if an earlier concurrent rotation created duplicates.
WITH ranked AS (
    SELECT id,row_number() OVER(PARTITION BY tg_user_id ORDER BY id DESC) n
    FROM reseller_api_keys WHERE is_active=1
)
UPDATE reseller_api_keys SET is_active=0 FROM ranked WHERE ranked.id=reseller_api_keys.id AND ranked.n>1;
CREATE UNIQUE INDEX reseller_one_active_key ON reseller_api_keys(tg_user_id) WHERE is_active=1;
ALTER TABLE reseller_api_keys ADD CONSTRAINT reseller_key_active_check CHECK(is_active IN (0,1)) NOT VALID;
CREATE TRIGGER reseller_customer_identity BEFORE INSERT OR UPDATE OF user_id,tg_user_id ON reseller_api_keys
FOR EACH ROW EXECUTE FUNCTION validate_customer_identity();
