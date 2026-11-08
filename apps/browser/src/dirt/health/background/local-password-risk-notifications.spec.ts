import { mock } from "jest-mock-extended";

import { AuthService } from "@bitwarden/common/auth/abstractions/auth.service";
import { AuthenticationStatus } from "@bitwarden/common/auth/enums/authentication-status";
import { I18nService } from "@bitwarden/common/platform/abstractions/i18n.service";
import { LogService } from "@bitwarden/common/platform/abstractions/log.service";
import { SystemNotificationsService } from "@bitwarden/common/platform/system-notifications";
import { mockAccountServiceWith } from "@bitwarden/common/spec";
import { PasswordStrengthService } from "@bitwarden/common/tools/password-strength";
import { UserId } from "@bitwarden/common/types/guid";
import { CipherService } from "@bitwarden/common/vault/abstractions/cipher.service";
import { CipherType } from "@bitwarden/common/vault/enums/cipher-type";
import { CipherView } from "@bitwarden/common/vault/models/view/cipher.view";
import { LoginView } from "@bitwarden/common/vault/models/view/login.view";

import { LocalPasswordRiskNotifications } from "./local-password-risk-notifications";

describe("LocalPasswordRiskNotifications", () => {
  const userId = "user" as UserId;
  const authService = mock<AuthService>();
  const cipherService = mock<CipherService>();
  const notifications = mock<SystemNotificationsService>();
  const i18nService = mock<I18nService>();
  let service: LocalPasswordRiskNotifications;

  function login(id: string, password: string): CipherView {
    return Object.assign(new CipherView(), {
      id,
      type: CipherType.Login,
      login: Object.assign(new LoginView(), { password }),
    });
  }

  beforeEach(() => {
    jest.resetAllMocks();
    authService.getAuthStatus.mockResolvedValue(AuthenticationStatus.Unlocked);
    notifications.isSupported.mockReturnValue(true);
    i18nService.t.mockImplementation((key) => key);
    service = new LocalPasswordRiskNotifications(
      mockAccountServiceWith(userId),
      authService,
      cipherService,
      new PasswordStrengthService(),
      i18nService,
      mock<LogService>(),
      () => notifications,
    );
  });

  it("reports local risks without revealing vault data and throttles concurrent reminders", async () => {
    const filled = login("filled", "password");
    cipherService.getAllDecrypted.mockResolvedValue([filled, login("duplicate", "password")]);

    await Promise.all([
      service.notifyAfterFill(filled, userId),
      service.notifyAfterFill(filled, userId),
    ]);

    expect(notifications.create).toHaveBeenCalledTimes(1);
    expect(notifications.create).toHaveBeenCalledWith({
      id: "local-vault-password-risk",
      title: "atRiskPassword",
      body: "localPasswordWeakAndReused",
      buttons: [],
    });
  });

  it("does not decrypt the vault for an organization item or a locked account", async () => {
    const filled = login("filled", "password");
    filled.organizationId = "organization";
    await service.notifyAfterFill(filled, userId);

    authService.getAuthStatus.mockResolvedValue(AuthenticationStatus.Locked);
    await service.notifyAfterFill(login("filled", "password"), userId);

    expect(cipherService.getAllDecrypted).not.toHaveBeenCalled();
    expect(notifications.create).not.toHaveBeenCalled();
  });

  it("does not display a reminder when the filled item no longer belongs to the active vault", async () => {
    cipherService.getAllDecrypted.mockResolvedValue([login("other", "password")]);

    await service.notifyAfterFill(login("filled", "password"), userId);

    expect(notifications.create).not.toHaveBeenCalled();
  });
});
