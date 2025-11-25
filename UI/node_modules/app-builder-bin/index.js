"use strict"

const path = require("path")

function getPath() {
  if (process.env.USE_SYSTEM_APP_BUILDER === "true") {
    return "app-builder"
  }

  if (!!process.env.CUSTOM_APP_BUILDER_PATH) {
    return path.resolve(process.env.CUSTOM_APP_BUILDER_PATH)
  }

  const { platform, arch } = process;
  if (platform === "darwin") {
    return path.join(__dirname, "mac", `app-builder_${arch === "x64" ? "amd64" : arch}`)
  }
  else if (platform === "win32") {
    return path.join(__dirname, "win", arch, "app-builder.exe")
  }
  else {
    return path.join(__dirname, "linux", arch, "app-builder")
  }
}

exports.appBuilderPath = getPath()
