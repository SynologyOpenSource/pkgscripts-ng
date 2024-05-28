#!/usr/bin/env python
#-*- coding: utf-8 -*-

import os
import json
import re
import copy
from argparse import ArgumentParser

class Parser:
	def __init__ (self, jsPath, makeGoal, appPrefix):
		self.jsPath = jsPath
		self.makeGoal = makeGoal
		appPrefixOr = re.sub(r'\s+', '|', appPrefix)
		print(appPrefixOr)
		rePatterns = [
			'(?://\s*@require\s*:\s*([\w\-_.]+))', # require
			'(?:Ext\.define\s*\(\s*[\'\"]([\w\-_.]+))', # define
			'(?:extend\s*:\s*\(*[\'\"]([\w\-_.]+))', # extend
			'(?:([\w\-_.]+)\s*=\s*Ext.extend\s*\(\s*([\w\-_.]+))', # define2, extend2
			'(?:((?:{})[\w\-_.]+)\s*=[^=])'.format(appPrefixOr), # define3
			'(?://\s*@define\s*:\s*([\w\-_.]+))' # define4
		]
		self.matchRe = re.compile('|'.join(rePatterns))
		self.replaceRe = re.compile('\/([^\/]+)$')
		prefixNames = appPrefix.split(" ")

		self.ourRe = re.compile('^({})'.format(appPrefixOr))

	def run (self):
		if len(self.makeGoal) == 0 or self.makeGoal == 'all' or self.makeGoal == 'JSCompress' or self.makeGoal == 'JSCompress_AutoConfig':
			self.make()
		if self.makeGoal == 'clean':
			self.clean()

	def make (self):
		self.clean()
		jsFiles = self.getJSFiles()
		print("Auto config js files:")
		print(jsFiles)
		self.parseRequire(jsFiles)

	def clean (self):
		return os.system('/usr/bin/find -L ' + self.jsPath + ' -name auto_config.debug -exec rm -f {} \\;')

	def getJSFiles (self):
		return os.popen('/usr/bin/find -L {} -name "*.js"'.format(self.jsPath)).read().strip().split('\n')

	def parseRequire (self, jsFiles):
		generatedPath = 'auto_config.debug'
		debugConfig = {}

		for jsFile in jsFiles:
			with open(jsFile) as file:
				fnDefs = self.getFnDefs(file.read())
			debugConfig[jsFile] = self.mixAppConfig(jsFile, fnDefs)

		self.jsonToFile(debugConfig, generatedPath)

	def getMatchResult(self, js):
		matchRec = self.matchRe.findall(js)
		result = []

		for require, define, extend, define2, extend2, define3, define4 in matchRec:
			if len(require) > 0:
				result.append(('require', None, require))
			elif len(define) > 0:
				result.append(('define', define, None))
			elif len(extend) > 0:
				last = result.pop()
				result.append(('define', last[1], extend))
			elif len(define2) > 0:
				result.append(('define', define2, extend2))
			elif len(define3) > 0:
				result.append(('define', define3, None))
			elif len(define4) > 0:
				result.append(('define', define4, None))

		return result

	def getFnDefs (self, js):
		matches = self.getMatchResult(js)
		fnDefs = {}
		requires = []

		for rule, fn, depend in matches:
			if rule == 'require':
				requires.append(depend)
			elif rule == 'define':
				fnDefs[fn] = requires
				requires = []
				if (depend):
					self.prependExtends(fnDefs[fn], depend)

		return fnDefs

	def prependExtends (self, requires, extends):
		if self.isOurExtends(extends):
			requires.insert(0, extends)

	def isOurExtends (self, extends):
		return self.ourRe.search(extends)

	def mixAppConfig (self, jsFile, fnDefs):
		appConfPath = 'app.config'
		conf = {}

		try:
			appConf = self.fileToJson(appConfPath)
		except:
			print('[Warning] no {} file or failed to parse into json'.format(appConfPath))
			appConf = {}

		for fnName, dependencies in fnDefs.iteritems():
			conf[fnName] = {}
			if fnName in appConf:
				conf[fnName] = copy.deepcopy(appConf[fnName])

			conf[fnName]['depend'] = dependencies

		return conf;

	def fileToJson (self, path):
		with open(path) as file:
			return json.load(file)

	def jsonToFile (self, js, path):
		with open(path, 'w') as file:
			json.dump(js, file, indent=2)

def Main ():
	parser = ArgumentParser(description='Chat @require to Config debug tool')
	parser.add_argument('--makegoal', metavar='makegoals', type=str, help='your MAKECMDGOALS')
	parser.add_argument('jspath', metavar='js-path', type=str, help='yout js path')
	parser.add_argument('appprefix', metavar='app-prefix', type=str, help='application prefix (e.g. SYNO.SDS.Chat)')
	options = parser.parse_args()

	parser = Parser(jsPath=options.jspath, makeGoal=options.makegoal, appPrefix=options.appprefix)
	parser.run()

Main()

