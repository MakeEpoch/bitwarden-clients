import { firstValueFrom } from "rxjs";

import { AccountService } from "@bitwarden/common/auth/abstractions/account.service";
import { AuthService } from "@bitwarden/common/auth/abstractions/auth.service";
import { AuthenticationStatus } from "@bitwarden/common/auth/enums/authentication-status";
import { I18nService } from "@bitwarden/common/platform/abstractions/i18n.service";
import { LogService } from "@bitwarden/common/platform/abstractions/log.service";
import { SystemNotificationsService } from "@bitwarden/common/platform/system-notifications";
import { PasswordStrengthServiceAbstraction } from "@bitwarden/common/tools/password-strength";
import { UserId } from "@bitwarden/common/types/guid";
import { CipherService } from "@bitwarden/common/vault/abstractions/cipher.service";
import { CipherView } from "@bitwarden/common/vault/models/view/cipher.view";
import { isRiskableLoginCipher } from "@bitwarden/common/vault/services/default-cipher-risk.service";

const REMINDER_INTERVAL_MS = 15 * 60 * 1000;

export class LocalPasswordRiskNotifications {
  private lastNotification: { userId: string; at: number } | undefined;

  constructor(
    private readonly accountService: AccountService,
    private readonly authService: AuthService,
    private readonly cipherService: CipherService,
    private readonly passwordStrengthService: PasswordStrengthServiceAbstraction,
    private readonly i18nService: I18nService,
    private readonly logService: LogService,
    private readonly notifications: () => SystemNotificationsService,
  ) {}

  async notifyAfterFill(cipher: CipherView, userId: UserId): Promise<void> {
    try {
      if (
        cipher.organizationId != null ||
        !isRiskableLoginCipher(cipher) ||
        !this.notifications().isSupported()
      ) {
        return;
      }
      const account = await firstValueFrom(this.accountService.activeAccount$);
      if (
        account?.id !== userId ||
        this.recentlyNotified(account.id) ||
        (await this.authService.getAuthStatus(account.id)) !== AuthenticationStatus.Unlocked
      ) {
        return;
      }

      const logins = await this.cipherService.getAllDecrypted(account.id);
      const password = cipher.login.password;
      // The current unlocked account must still own the item that was filled.
      if (
        !logins.some(
          (login) =>
            login.id === cipher.id &&
            login.organizationId == null &&
            isRiskableLoginCipher(login) &&
            login.login.password === password,
        )
      ) {
        return;
      }

      const weak =
        this.passwordStrengthService.getPasswordStrength(password, undefined, [
          cipher.login.username ?? "",
        ]).score < 3;
      const reused = logins.some(
        (other) =>
          other.id !== cipher.id &&
          other.organizationId == null &&
          isRiskableLoginCipher(other) &&
          other.login.password === password,
      );

      if (
        (!weak && !reused) ||
        (await this.authService.getAuthStatus(account.id)) !== AuthenticationStatus.Unlocked ||
        (await firstValueFrom(this.accountService.activeAccount$))?.id !== account.id ||
        this.recentlyNotified(account.id)
      ) {
        return;
      }

      // A stable ID replaces a prior notification and reveals no item or site information.
      this.lastNotification = { userId: account.id, at: Date.now() };
      await this.notifications().create({
        id: "local-vault-password-risk",
        title: this.i18nService.t("atRiskPassword"),
        body: this.i18nService.t(
          weak && reused
            ? "localPasswordWeakAndReused"
            : weak
              ? "localPasswordWeak"
              : "localPasswordReused",
        ),
        buttons: [],
      });
    } catch {
      // A reminder failure must never interrupt autofill or log vault data.
      this.logService.warning("Local password risk reminder failed.");
    }
  }

  private recentlyNotified(userId: string): boolean {
    return (
      this.lastNotification?.userId === userId &&
      Date.now() - this.lastNotification.at < REMINDER_INTERVAL_MS
    );
  }
}
