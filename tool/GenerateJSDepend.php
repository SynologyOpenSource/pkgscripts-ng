#!/usr/bin/php
<?php

/* Decode json file to php object */
function DecodeJsonFile($file)
{
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

/* Get all dependency from one js file. e.g. */
/*
fn = "js/abc.js": {
		"SYNO.AAA": {
			"depend" : [
				"SYNO.Parent"
			]
		},
		"SYNO.BBB" : {
			"depend" : [
				"SYNO.Father"
			]
		}
	}
input -->
	fn["js/abc.js"]
output -->
	["SYNO.Parent", "SYNO.Father"]
 */
function MergeDependency($fnList)
{
	$depend = array();
	foreach ($fnList as $fnName => $fnConfig) {
		if (is_array($fnConfig['depend'])) {
			$depend = array_merge($depend, $fnConfig['depend']);
		}
	}
	return array_unique($depend);
}

function FindSrcFileForFn($fnName)
{
	global $ConfigDebug;
	foreach ($ConfigDebug as $srcFile => $fileConfig) {
		if (isSet($fileConfig[$fnName])) {
			return $srcFile;
		}
	}
	return FALSE;
}

function PostTraversalDependency($file, $depend, &$queue)
{
	if (FALSE !== array_search($file, $queue)) {
		return;
	}

	if (is_array($depend[$file])) {
		foreach ($depend[$file] as $depFn) {
			$depFile = FindSrcFileForFn($depFn);
			if (FALSE === $depFile || $file === $depFile) {
				continue;
			}
			PostTraversalDependency($depFile, $depend, $queue);
		}
	}

	if (isSet($depend[$file])) {
		$queue[] = $file;
	}
}

function Usage()
{
	global $argv;

	echo <<<EOD
Usage: {$argv[0]} module_dir

EOD;
}

/* ----------------------- */
/* ----------------------- */
/* main access entry point */
/* ----------------------- */
/* ----------------------- */


if (!is_dir($argv[1])) {
	echo "Error: {$argv[1]} is not a directory.\n";
	Usage();
	exit(1);
}

$CWD = getcwd();
chdir($argv[1]);

$InputFiles = array(
	'debug'		=>	'config.debug',
	'define'	=>	'config.define',
	'auto_debug'	=>	'auto_config.debug'
);

$OutputFiles = array(
	'config'	=>	'config',
	'depend'	=>	'config.depends'
);

$JSInfo = array();
$Config = array();

$define_path = $InputFiles['define'];

if (file_exists($define_path)) {
	$ConfigDefine = DecodeJsonFile($define_path);
} else {
	echo "Skip parsing: config.define not exist in config.depends\n";
	$ConfigDefine = array();
}

/* try to read from auto config path */
if (file_exists($InputFiles['debug'])) {
	$ConfigDebug = DecodeJsonFile($InputFiles['debug']);
} else if (file_exists($InputFiles['auto_debug'])) {
	$ConfigDebug = DecodeJsonFile($InputFiles['auto_debug']);
} else {
	echo "Skip parsing: config.debug and auto_config.debug not exist\n";
	$ConfigDebug = array();
}

if (!is_array($ConfigDebug) || !is_array($ConfigDefine)) {
	exit(1);
}

/* merge config, parse fn and dependency info */
foreach ($ConfigDefine as $dstFile => $srcFiles) {
	$Config[$dstFile] = array();
	$JSInfo[$dstFile] = array('jsFiles' => array(), 'fnList' => array(), 'params' => null);

	$srcJsFiles = array();
	if (isSet($srcFiles['JSfiles'])) { /* with parameters */
		$srcJsFiles = $srcFiles['JSfiles'];
	} else {
		$srcJsFiles = $srcFiles;
	}

	foreach ($srcJsFiles as $files) {
		foreach(glob($files) as $file) {
			if (!isSet($ConfigDebug[$file])) {
				$ConfigDebug[$file] = array();
			}
			$Config[$dstFile] = array_merge($Config[$dstFile], $ConfigDebug[$file]);
			$JSInfo[$dstFile]['jsFiles'][$file] = MergeDependency($ConfigDebug[$file]);
			$JSInfo[$dstFile]['fnList'] = array_merge($JSInfo[$dstFile]['fnList'], array_keys($ConfigDebug[$file]));
			if (isSet($srcFiles['params'])) {
				$JSInfo[$dstFile]['params'] = $srcFiles['params'];
			}
		}
	}
}

/* copy virtual config */
if (isSet($ConfigDebug['.url'])) {
	$Config['.url'] = $ConfigDebug['.url'];
}

/* Resolve JS compress dependency */
foreach ($JSInfo as $dstFile => &$dstConfig) {
	$queue = array();
	foreach (array_keys($dstConfig['jsFiles']) as $file) {
		PostTraversalDependency($file, $dstConfig['jsFiles'], $queue);
	}

	if(isSet($JSInfo[$dstFile]['params'])) {
		$JSInfo[$dstFile] = array('files' => $queue, 'params' => $JSInfo[$dstFile]['params']);
	} else {
		$JSInfo[$dstFile] = $queue;
	}
}

function getFlattenDepList($dstConfig, $comp) {
	$dependList = array();
	if (array_key_exists('depend', $comp)) {
		foreach ($comp['depend'] as $item) {
			if (array_key_exists($item, $dstConfig)) {
				// internal depend => get its depend list
				$flatDep = getFlattenDepList($dstConfig, $dstConfig[$item]);
				$dependList = array_merge($flatDep, $dependList);
				$dependList = array_values(array_unique($dependList));
			} else {
				$dependList[] = $item;
			}
		}
	}

	return $dependList;
}

/* flatten dependency */
if ($argv[2] != "") {
	echo "Flatten Dependency...\n";
	foreach ($Config as $dstFile => &$dstConfig) {
		foreach ($dstConfig as $comp => &$compConfig) {
			if (array_key_exists('depend', $compConfig)) {
				$dependList = getFlattenDepList($dstConfig, $compConfig);

				if (count($dependList) === 0) {
					unset($compConfig['depend']);
				} else {
					$compConfig['depend'] = $dependList;
				}
			}
		}
	}
	echo "Flatten Dependency Done...\n";
}

function GenerateConfig()
{
	global $Config;

	$result = json_encode($Config);
	if( (function_exists("get_magic_quotes_gpc") && get_magic_quotes_gpc()) ||
		(ini_get('magic_quotes_sybase') && (strtolower(ini_get('magic_quotes_sybase')) != "off" )) ) {
		$result = stripslashes($result);
	}
	return $result;
}

file_put_contents($OutputFiles['depend'], json_encode($JSInfo));

if (count($Config) > 0) {
	file_put_contents($OutputFiles['config'], GenerateConfig());
}

exit(0);
?>

