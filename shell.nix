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
}
