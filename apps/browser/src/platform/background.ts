import { ConsoleLogService } from "@bitwarden/common/platform/services/console-log.service";

import { registerLocalUpdateChecks } from "../background/local-updates";
import MainBackground from "../background/main.background";

const logService = new ConsoleLogService(false);
const bitwardenMain = ((self as any).bitwardenMain = new MainBackground());
const startup = bitwardenMain.bootstrap();
startup.catch((error) => logService.error(error));
registerLocalUpdateChecks(startup);
