სად არის ზიპები?

Mac:
  SlapYourMac-mac.zip — macOS-ზე იქმნება scripts/make_mac_release_zip.sh-ით ან ხელით zip dist/SlapYourMac.app

Windows — სამ გზით:
  1) ლოკალური PC: scripts/setup_and_build_windows.ps1 → releases/SlapYourMac-windows.zip
  2) GitHub: Actions → „Build Windows zip“ → გაუშვი → იღები Artifacts-იდან (PyInstaller იწყება Windows runner-ზე)
  3) იგივე workflow ტეგ v* push-ით GitHub Releases-ში არქივადაც შენცვლის zip-ს („ერთი ბმული“ მეგობლებს)

Where?
- mac: scripts/make_mac_release_zip.sh → releases/SlapYourMac-mac.zip
- win: locally setup_and_build_windows.ps1, or repo Actions / tagged Release (see README)
