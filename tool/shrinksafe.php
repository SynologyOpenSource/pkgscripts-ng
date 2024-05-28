#!/usr/bin/php
<?php

$JRE = "/usr/lib/jvm/java-6-jdk/bin/java";
$JSLINT = "/usr/local/tool/jslint+rhino.jar";
$RhinoCompressor = "/usr/local/tool/custom_rhino.jar";
$ClosureCompiler = "/usr/local/tool/closurecompiler.jar";
$YUICompressor = "/usr/local/tool/yuicompressor-2.4.2.jar";
$VerboseMsg = false;

$COPYRIGHT = "/* Copyright (c) " . date("Y") . " Synology Inc. All rights reserved. */\n\n";

$JSLINT_IGNORE = array("/variable .* declared in a block/",
						"/.* is better written in dot notation/",
						"/Use .* to compare with/",
						"/Line breaking error/",
						"/A constructor name should start with an uppercase letter/",
						"/Missing 'new' prefix when invoking a constructor/",
						"/Use the array literal notation*/",
						"/JavaScript URL./",
						"/document.write/",
						"/eval/");


function ShouldIgnoreJSLintError($desc)
{
	global $JSLINT_IGNORE;
	foreach($JSLINT_IGNORE as $pattern) {
		if (preg_match($pattern, $desc)) {
			return true;
		}
	}
	return false;
}

function FindJSHintComments($fileList) {
	echo "== begin of JSHint comments ==\n";

	$cmd = "grep -n ' jshint ' $fileList";
	system($cmd);
	$cmd = "grep -n ' global ' $fileList";
	system($cmd);
	echo "== end of JSHint comments ==\n";
}

function ValidateJSFiles($linter, $jsFiles) {
	global $JRE, $JSLINT, $VerboseMsg;

	$errors = 0;
	$fileList = implode(' ', $jsFiles);

	if ($linter === "rhino-jslint") {
		$cmd = sprintf("%s -jar %s %s", $JRE, $JSLINT, $fileList);
	} elseif ($linter === "jslint") {
		$cmd = sprintf("/usr/bin/jslint --white --terse %s", $fileList);
	} elseif ($linter === "jshint") {
		$cmd = sprintf("/usr/bin/jshint %s", $fileList);

		if ($VerboseMsg) {
			FindJSHintComments($fileList);
		}
	} elseif ($linter === "eslint") {
		$cmd = sprintf("/usr/bin/eslint --color %s", $fileList);
	}

	$handle = popen($cmd, "r");
	if (false === $handle) {
		echo "Failed to execute [".$cmd."]\n";
		return 1;
	}
	while (!feof($handle)) {
		$line = fgets($handle);
		$line = trim($line);
		if (!$line) {
			continue;
		}
		if ($linter === "rhino-jslint") {
			list($prog, $file, $lineno, $err, $desc) = explode(":", $line);
			$invalidLine = !ShouldIgnoreJSLintError($desc);
		} else {
			$invalidLine = true;
		}
		if ($invalidLine) {
			$errors++;
		}
		if ($invalidLine || $VerboseMsg) {
			echo $line ."\n";
		}
	}
	pclose($handle);
	return $errors;
}

function CombineJSFiles($outFile, $jsFiles)
{
	foreach ($jsFiles as $file) {
		$fileContent = file_get_contents($file);
		/* append newline to end of file in case last line is comment */
		if ($fileContent !== false && substr($fileContent, -1) !== "\n") {
			$fileContent .= "\n";
		}
		file_put_contents($outFile, $fileContent, FILE_APPEND);
	}
}

function RhinoCompress($outFile, $jsFile)
{
	global $JRE, $RhinoCompressor;
	$cmd = sprintf("%s -jar %s -c %s",
				   escapeshellcmd($JRE), escapeshellarg($RhinoCompressor),
				   escapeshellarg($jsFile));
	$handle = popen($cmd, "r");

	/* custom_rhino.jar won't trim line-break */
	$fp = fopen($outFile, "a");
	while (!feof($handle)) {
		fwrite($fp, trim(fgets($handle)));
	}
	fclose($fp);

	pclose($handle);
}

/* Transpiler */

function TranspileJSFiles($transpiler, $outFile, $jsFiles)
{
	$retCode = -1;

	$tmpFile = getcwd()."/.jsTmp_" . strtr($outFile, "/", "_") . ".js";
	CombineJSFiles($tmpFile, $jsFiles);
	$retCode = $transpiler($outFile, $tmpFile);
	@unlink($tmpFile);

	return $retCode;
}

function BabelTranspile($outFile, $jsFile)
{
	$retCode = -1;

	$cmd = sprintf("babel %s -o %s", escapeshellarg($jsFile), escapeshellarg($outFile));
	system($cmd, $retCode);

	return $retCode;
}

function SkipTranspile($outFile, $jsFile)
{
	$retCode = -1;

	$cmd = sprintf("mv %s %s", escapeshellarg($jsFile), escapeshellarg($outFile));
	system($cmd, $retCode);

	return $retCode;
}

/* Compressor */

function ClosureCompile($outFile, $jsFile)
{
	global $JRE, $ClosureCompiler;
	$cmd = sprintf("%s -jar %s --warning_level QUIET --js %s >>%s",
				   escapeshellcmd($JRE), escapeshellarg($ClosureCompiler),
				   escapeshellarg($jsFile), escapeshellarg($outFile));
	system($cmd);
}

function YUICompress($outFile, $jsFile)
{
	global $JRE, $YUICompressor;
	$cmd = sprintf("%s -jar %s %s >>%s",
				   escapeshellcmd($JRE), escapeshellarg($YUICompressor),
				   escapeshellarg($jsFile), escapeshellarg($outFile));
	system($cmd);
}

function UglifyjsCompress($outFile, $jsFile)
{
	$cmd = sprintf("/usr/bin/uglifyjs --comments '/license/i' -m -c drop_console,warnings=false %s >> %s",
				escapeshellarg($jsFile), escapeshellarg($outFile));

	system($cmd);
}

function TerserCompress($outFile, $jsFile)
{
	$cmd = sprintf("/usr/bin/terser --comments '/license/i' -m -c drop_console,warnings=false %s >> %s",
				escapeshellarg($jsFile), escapeshellarg($outFile));

	system($cmd);
}

function SkipCompress($outFile, $jsFile)
{
    $cmd = sprintf("mv %s %s",
                escapeshellarg($jsFile), escapeshellarg($outFile));

    system($cmd);
}

function CompressJSFiles($compressor, $outFile, $transpiledFile)
{
	global $COPYRIGHT;

	file_put_contents($outFile, $COPYRIGHT);

	$compressor($outFile, $transpiledFile);
	@unlink($transpiledFile);
}

function GetOptions()
{
	global $argv;

	$options = "svdc:l:t:";
	$opts = getopt($options);
	foreach( $opts as $o => $a )
	{
		while ( $k = array_search( "-" . $o, $argv ) ) {
			if ( $k )
				unset( $argv[$k] );
			if ( preg_match( "/^.*".$o.":.*$/i", $options ) )
				unset( $argv[$k+1] );
		}
	}
	$argv = array_merge( $argv );
	return $opts;
}

function ShowMessage($msg)
{
	global $VerboseMsg;

	if (!$VerboseMsg) {
		return;
	}
	echo $msg . "\n";
}

function Usage()
{
	global $argv;

	echo <<<EOD
USAGE:
	{$argv[0]} [-d] output config.depends
	{$argv[0]} [-s|-l] [-tc] [-v] output input [...]

OPTIONS:
	-d: Read JS dependency from config depend file
	-s: Skip JavaScript Validation (will ignore -l)
	-t Transpiler:
		babel:  Convert ES6+ code into a backwards compatible version
		skip: Don't do any transpile (default)
	-c Compressor:
		rhino: old compressor
		closure: Google Closure Compiler
		uglifyjs: UglifyJs Compressor
		yui: Yahoo YUI Compressor (default)
		terser: JavaScript parser, mangler, optimizer and beautifier toolkit for ES6+
		skip: do not use any compressor
	-l Linter:
		rhino-jslint: old linter
		jslint: node-jslint
		jshint: node-jshint (default)
		eslint: eslint for ES6/JSX syntax
		skip: skip JavaScript validation
	-v:
		show verbose message, including full JSLint messages.

EOD;
}

/* Decode json file to php object */
function DecodeJsonFile($file)
{
	print($file."\n");
	$content = @file_get_contents($file);
	if (FALSE === $content) {
		echo $file . ": Read error.\n";
		return NULL;
	}

	$result = json_decode($content, true);
	if (!is_array($result)) {
		echo $file . ": Json parse failed.\n";
	}
	return $result;
}

function SetTranspiler($opts)
{
	$transpiler = SkipTranspile;

	if (isSet($opts['t'])) {
		switch ($opts['t']) {
		case 'babel':
			if (!file_exists("/usr/bin/babel")) {
				echo "Error: Babel not found, available after DSM6.2\n";
				exit(1);
			}
			$transpiler = BabelTranspile;
			break;
		case 'skip':
			$transpiler = SkipTranspile;
			break;
		default:
			echo "Error: Invalid Transpiler Option.\n";
			Usage();
			exit(1);
		}
		if ('skip' != $opts['t']) {
			echo "Transpile using [".$opts['t']."]\n";
		}
	}

	return $transpiler;
}

function SetCompressor($opts)
{
	$compressor = YUICompress;
	if (isSet($opts['c'])) {
		switch ($opts['c']) {
		case 'rhino':
			$compressor = RhinoCompress;
			break;
		case 'closure':
			$compressor = ClosureCompile;
			break;
		case 'yui':
			$compressor = YUICompress;
			break;
		case 'uglifyjs':
			$compressor = UglifyjsCompress;
			break;
		case 'terser':
			$compressor = TerserCompress;
			break;
		case 'skip':
			$compressor = SkipCompress;
			break;
		default:
			echo "Error: Invalid Compressor Option.\n";
			Usage();
			exit(1);
		}
		if ('skip' != $opts['c']) {
			echo "Compress using [".$opts['c']."]\n";
		}
	} else {
		echo "Compress using [yui]\n";
	}
	return $compressor;
}

function SetLinter($opts)
{
	$linter = 'jshint';
	if (isset($opts['l'])) {
		$linter = $opts['l'];
	}
	return $linter;
}

function RunLinter($opts, $linter, $jsFiles)
{
	if (!isSet($opts['s']) && "skip" != $linter) {
		echo "Validating JS using [$linter]...\n";
		if ($linter === "eslint" && !file_exists("/usr/bin/eslint")) {
			echo "Error: Compressor [eslint] only avaliable since DSM7.0\n";
			exit(1);
		}
		if (ValidateJSFiles($linter, $jsFiles) > 0) {
			exit(1);
		}
	} else {
		echo "Skip JavaScript Validation\n";
	}
}

function RunTranspiler($transpiler, $jsFiles, $transpiledOutFile)
{
	$retCode = TranspileJSFiles($transpiler, $transpiledOutFile, $jsFiles);
	if (0 != retCode) {
		throw new Exception("ERROR >> Failed to transpile [".$transpiledOutFile."]\n");
	}
}

function RunCompressor($compressor, $outFile, $transpiledOutFile)
{
	CompressJSFiles($compressor, $outFile, $transpiledOutFile);
}

/* main process */

$opts = GetOptions();

if (FALSE === $opts || count($argv) < 3) {
	Usage();
	exit(1);
}

$VerboseMsg = isSet($opts['v']);
$transpiler = SetTranspiler($opts);
$compressor = SetCompressor($opts);
$linter     = SetLinter($opts);

/* read depend js file */

$outFile = $argv[1];

if(isSet($opts['d'])) {
	$jsDepCfg = DecodeJsonFile($argv[2]);

	if (!is_array($jsDepCfg)) {
		exit(1);
	}

	if (!is_array($jsDepCfg[$outFile])) {
		echo "Error > ".$outFile." is not in config.depends\n";
		exit(1);
	}

	if(isSet($jsDepCfg[$outFile]['files'])) {
		$jsFiles = $jsDepCfg[$outFile]['files'];
	} else {
		$jsFiles = $jsDepCfg[$outFile];
	}
} else {
	$jsFiles = array_slice($argv, 2);
}

$transpiledOutFileOrig = tempnam("/tmp/", basename($outFile)."_transpiled_");
$transpiledOutFile = $transpiledOutFileOrig.'.js';

try {
	RunLinter($opts, $linter, $jsFiles);
	RunTranspiler($transpiler, $jsFiles, $transpiledOutFile);
	RunCompressor($compressor, $outFile, $transpiledOutFile);
} catch(Exception $e) {
	echo $e->getMessage();
}

@unlink($transpiledOutFileOrig);
@unlink($transpiledOutFile);
?>

