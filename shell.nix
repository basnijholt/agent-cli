# nix-direnv file
{ pkgs ? import <nixpkgs> {}}:

pkgs.mkShell {
  packages = [
    pkgs.portaudio
    pkgs.ffmpeg
    pkgs.pkg-config
    pkgs.gcc
    pkgs.python3
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath [ pkgs.portaudio ]}:$LD_LIBRARY_PATH
  '';
}
