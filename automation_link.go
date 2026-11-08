//go:build e2e

package main

// Linking the automation plugin only in e2e builds lets an external driver
// (mygo-automation) inspect and drive the UI in verification runs. Release
// builds omit the tag and never listen.
import _ "github.com/egoist/mygo/plugins/automation"
