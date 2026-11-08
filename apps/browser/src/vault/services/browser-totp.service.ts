import { TotpService } from "@bitwarden/common/vault/services/totp.service";

export class BrowserTotpService extends TotpService {
  override readonly canGenerateForPersonalVault = true;
}
