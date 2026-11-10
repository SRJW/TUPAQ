// Read-only parser experiment on macOS. No media-library or network operations.
// Declarations are checked against the runtime before invoking the parser.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

@interface NSObject (TUPAQLyricsParserDeclarations)
- (instancetype)initWithTTMLData:(NSData *)data;
- (id)parseWithError:(NSError *__autoreleasing *)error;
@end

static id value(id object, NSString *key) {
    if (!object || ![object respondsToSelector:NSSelectorFromString(key)]) return [NSNull null];
    @try { return [object valueForKey:key] ?: [NSNull null]; }
    @catch (NSException *exception) { return [NSNull null]; }
}

static id number(id object, NSString *key) {
    id item = value(object, key);
    return [item isKindOfClass:[NSNumber class]] && isfinite([item doubleValue]) ? item : [NSNull null];
}

static BOOL writeReport(NSDictionary *report, NSString *path) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:NULL];
    return data && [data writeToFile:path atomically:YES];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 3) return 2;
        NSString *inputPath = [NSString stringWithUTF8String:argv[1]];
        NSString *outputPath = [NSString stringWithUTF8String:argv[2]];
        NSData *inputData = [NSData dataWithContentsOfFile:inputPath];
        if (!inputData || inputData.length > 128 * 1024) return 2;
        id input = [NSJSONSerialization JSONObjectWithData:inputData options:0 error:NULL];
        if (![input isKindOfClass:[NSDictionary class]]) return 2;
        NSString *xml = input[@"xml"];
        if (![xml isKindOfClass:[NSString class]] || xml.length > 16384 ||
            [xml rangeOfString:@"<!DOCTYPE" options:NSCaseInsensitiveSearch].location != NSNotFound) return 2;

        NSError *loadError = nil;
        NSString *bundlePath = @"/System/Library/PrivateFrameworks/MediaServices.framework";
        NSBundle *bundle = [NSBundle bundleWithPath:bundlePath];
        BOOL loaded = bundle && [bundle loadAndReturnError:&loadError];
        Class parserClass = NSClassFromString(@"MSVLyricsTTMLParser");
        NSMutableDictionary *report = [@{
            @"os": [[NSProcessInfo processInfo] operatingSystemVersionString],
            @"framework_loaded": @(loaded), @"parser_available": @(parserClass != Nil),
            @"parsed": @NO, @"lines": @[], @"iphone_validation": @NO,
            @"framework": bundlePath
        } mutableCopy];
        if (loadError) report[@"load_error"] = @{@"domain": loadError.domain, @"code": @(loadError.code)};
        if (!parserClass) {
            NSMutableArray *candidates = [NSMutableArray array];
            unsigned int count = 0;
            Class *classes = objc_copyClassList(&count);
            for (unsigned int i = 0; i < count && candidates.count < 20; i++) {
                NSString *name = NSStringFromClass(classes[i]);
                if ([name hasPrefix:@"MSV"] && [name rangeOfString:@"Lyric" options:NSCaseInsensitiveSearch].location != NSNotFound)
                    [candidates addObject:name];
            }
            free(classes); report[@"candidate_classes"] = candidates;
            report[@"status"] = @"parser-unavailable";
            return writeReport(report, outputPath) ? 0 : 3;
        }
        Method initMethod = class_getInstanceMethod(parserClass, @selector(initWithTTMLData:));
        Method parseMethod = class_getInstanceMethod(parserClass, @selector(parseWithError:));
        char initReturn[32] = {0}, parseReturn[32] = {0};
        char initArgument[32] = {0}, parseArgument[32] = {0};
        if (initMethod) method_getReturnType(initMethod, initReturn, sizeof(initReturn));
        if (parseMethod) method_getReturnType(parseMethod, parseReturn, sizeof(parseReturn));
        if (initMethod) method_getArgumentType(initMethod, 2, initArgument, sizeof(initArgument));
        if (parseMethod) method_getArgumentType(parseMethod, 2, parseArgument, sizeof(parseArgument));
        const char *argument = parseArgument;
        while (*argument && strchr("rnNoORV", *argument)) argument++;
        if (!initMethod || !parseMethod || method_getNumberOfArguments(initMethod) != 3 ||
            method_getNumberOfArguments(parseMethod) != 3 || initReturn[0] != '@' || parseReturn[0] != '@' ||
            initArgument[0] != '@' || argument[0] != '^' || argument[1] != '@') {
            report[@"status"] = @"unqualified-method-signature";
            return writeReport(report, outputPath) ? 0 : 3;
        }
        @try {
            id parser = [[parserClass alloc] initWithTTMLData:[xml dataUsingEncoding:NSUTF8StringEncoding]];
            NSError *error = nil;
            id result = [parser parseWithError:&error];
            id info = [result respondsToSelector:@selector(lyricsLines)] ? result : value(parser, @"lyricsInfo");
            id rawLines = value(info, @"lyricsLines");
            if (![rawLines isKindOfClass:[NSArray class]]) rawLines = value(parser, @"lyricLines");
            NSMutableArray *lines = [NSMutableArray array];
            if ([rawLines isKindOfClass:[NSArray class]]) {
                for (id line in rawLines) {
                    if (lines.count >= 64) break;
                    id words = value(line, @"words");
                    [lines addObject:@{@"start": number(line, @"startTime"), @"end": number(line, @"endTime"),
                        @"type": number(line, @"type"),
                        @"word_count": [words isKindOfClass:[NSArray class]] ? @([words count]) : [NSNull null]}];
                }
            }
            report[@"parsed"] = @(result != nil && error == nil);
            report[@"result_class"] = result ? NSStringFromClass([result class]) : @"nil";
            report[@"info_type"] = number(info, @"type");
            report[@"lines"] = lines;
            report[@"status"] = error ? @"parse-error" : @"observed";
            if (error) report[@"error"] = @{@"domain": error.domain, @"code": @(error.code)};
        } @catch (NSException *exception) {
            report[@"status"] = @"exception";
            report[@"exception_class"] = NSStringFromClass([exception class]);
        }
        return writeReport(report, outputPath) ? 0 : 3;
    }
}
